"use strict";
const $ = id => document.getElementById(id);
const state = {stream:null, socket:null, running:false, demo:false, paused:false, generation:0,
  started:0, timer:null, frameTimer:null, demoTimer:null, watchdog:null, cueTimer:null,
  inFlight:false, reviewing:false, events:[], features:[], providerConfig:null};
const names = {chin_touch:"Chin & beard",face_touch:"Face touching",neck_touch:"Neck touching",movement:"Frequent movement"};
const canvas = document.createElement("canvas");
const ctx = canvas.getContext("2d");
const elapsed = () => Math.floor((performance.now() - state.started) / 1000);
const clock = seconds => `${Math.floor(seconds/60).toString().padStart(2,"0")}:${Math.floor(seconds%60).toString().padStart(2,"0")}`;
const enabled = () => [...document.querySelectorAll("[data-condition]:checked")].map(el=>el.dataset.condition);
function notice(message="") { $("notice").textContent=message; $("notice").hidden=!message; }
function settings() { return {enabled:state.paused?[]:enabled(),hold_seconds:Number($("hold-seconds").value),cooldown_seconds:Number($("cooldown-seconds").value),sensitivity:Number($("sensitivity").value)}; }
function syncSettings() {
  const sensitivity=Number($("sensitivity").value);
  $("sensitivity-value").textContent=sensitivity<.9?"Gentle":sensitivity>1.2?"Attentive":"Balanced";
  const selected=enabled();
  document.querySelector(".session-stats .stat-text").textContent=selected.length===1?names[selected[0]]:selected.length?`${selected.length} habits`:"No habits enabled";
  $("focus-caption").textContent=selected.length===1?"One small habit at a time":"Choose what matters to you";
  if(state.socket?.readyState===WebSocket.OPEN) state.socket.send(JSON.stringify({type:"settings",settings:settings()}));
  clearCue();
}
function refreshReview() { $("review-button").disabled=!state.running||state.demo||state.reviewing||!$("cloud-consent").checked; }
function clearCue() { clearTimeout(state.cueTimer); $("stage").classList.remove("alert-border"); $("buddy").classList.remove("nudging"); $("cue").hidden=true; }
function showCue(message) {
  if(state.paused) return;
  clearCue();
  const style=document.querySelector('[name="cue-style"]:checked').value;
  $("stage").classList.toggle("alert-border",style!=="avatar");
  $("buddy").hidden=style==="border";
  $("buddy").classList.toggle("nudging",style!=="border");
  $("buddy-expression").textContent="!";
  $("cue-text").textContent=message; $("cue").hidden=false;
  state.cueTimer=setTimeout(clearCue,4000);
}
function addEvent(condition,message,source="local") {
  const event={condition,message,source,seconds:elapsed()}; state.events.push(event);
  // Bound the in-memory event log during very long sessions.
  if(state.events.length>1000) state.events.shift();
  $("cue-count").textContent=String(state.events.length);
  $("activity-empty").hidden=true;
  const item=document.createElement("li");
  const timestamp=document.createElement("time");timestamp.textContent=clock(event.seconds);
  const text=document.createElement("span");text.className="event-message";text.textContent=message;
  const badge=document.createElement("span");badge.className="event-source";badge.textContent=source.toUpperCase();
  item.append(timestamp,text,badge);$("activity").prepend(item);
  while($("activity").children.length>30) $("activity").lastChild.remove();
  showCue(message);
}
function prepareSession(demo=false) {
  state.running=true; state.demo=demo;state.started=performance.now();state.events=[];state.features=[];state.paused=false;
  $("activity").replaceChildren();$("activity-empty").hidden=false;$("cue-count").textContent="0";
  $("welcome").hidden=true;$("demo-scene").hidden=!demo;$("camera").hidden=demo;
  $("camera-badge").hidden=demo;$("stop-button").disabled=false;$("pause-button").disabled=false;
  $("pause-button").querySelector(".button-label").textContent="Pause cues";$("recalibrate-button").disabled=demo;
  $("buddy").hidden=document.querySelector('[name="cue-style"]:checked').value==="border";
  $("session-state").textContent=demo?"CUE PREVIEW":"STARTING LOCAL DETECTOR";
  $("live-dot").classList.remove("idle");
  state.timer=setInterval(()=>$("session-time").textContent=clock(elapsed()),1000);
  refreshReview();
}
function stopSession(message="") {
  state.generation++;state.running=false;state.inFlight=false;state.reviewing=false;
  clearInterval(state.timer);clearTimeout(state.frameTimer);clearInterval(state.demoTimer);clearTimeout(state.watchdog);clearCue();
  if(state.socket){state.socket.onclose=null;state.socket.close();state.socket=null;}
  if(state.stream) state.stream.getTracks().forEach(track=>track.stop());
  state.stream=null;$("camera").srcObject=null;$("camera").hidden=true;
  $("demo-scene").hidden=true;$("welcome").hidden=false;$("buddy").hidden=true;
  $("calibration").hidden=true;$("camera-badge").hidden=true;
  $("stop-button").disabled=true;$("pause-button").disabled=true;$("recalibrate-button").disabled=true;
  $("start-button").disabled=false;$("start-button").querySelector(".button-label").textContent="Start my camera";
  $("live-dot").classList.add("idle");$("session-state").textContent="READY WHEN YOU ARE";
  $("tracking-status").textContent="Your camera is off";state.features=[];
  $("review-button").querySelector(".button-label").textContent=`Ask ${providerLabel()}`;refreshReview();
  if(message)notice(message);
}
async function startCamera() {
  stopSession();notice();const generation=state.generation;
  $("start-button").disabled=true;$("start-button").querySelector(".button-label").textContent="Opening camera…";
  try {
    const status=await fetch("/api/status").then(r=>{if(!r.ok)throw Error("Could not reach the Python server.");return r.json();});
    if(!status.local_ready) throw Error("Local models need setup. In the project terminal, run: uv run miyagi download-models");
    if(!navigator.mediaDevices?.getUserMedia) throw Error("Camera access requires localhost or HTTPS in a supported browser.");
    const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},facingMode:"user"},audio:false});
    if(generation!==state.generation){stream.getTracks().forEach(t=>t.stop());return;}
    state.stream=stream;$("camera").srcObject=stream;await $("camera").play();
    if(generation!==state.generation)return;
    stream.getVideoTracks()[0].onended=()=>stopSession("Camera access ended. You can start another session.");
    prepareSession();$("tracking-status").textContent="Warming up the local models…";
    const socket=new WebSocket(`${location.protocol==="https:"?"wss:":"ws:"}//${location.host}/ws/coach`);state.socket=socket;
    state.watchdog=setTimeout(()=>stopSession("The detector did not respond. Check model setup and restart."),30000);
    socket.onmessage=event=>{
      if(generation!==state.generation)return;
      let data;try{data=JSON.parse(event.data);}catch{stopSession("Invalid detector response.");return;}
      if(data.error){stopSession(data.error);return;}
      clearTimeout(state.watchdog);state.inFlight=false;
      if(data.ready){syncSettings();sendFrame(generation);return;}
      $("session-state").textContent=state.paused?"CUES PAUSED":data.tracking?"LOCAL COACHING IS ON":"LOOKING FOR YOU";
      $("tracking-status").textContent=!data.tracking?"Keep your face and hands in view":!data.calibrated?"Calibrating your baseline…":"Tracking locally · no recording";
      $("calibration").hidden=!data.tracking||data.calibrated;
      $("calibration-progress").value=data.calibration||0;
      if(data.features){state.features.push(data.features);if(state.features.length>16)state.features.shift();}else state.features=[];
      if(!state.paused) for(const alert of data.alerts||[]) addEvent(alert.condition,alert.message);
      state.frameTimer=setTimeout(()=>sendFrame(generation),125);
    };
    socket.onclose=()=>{if(generation===state.generation)stopSession("The local detector disconnected. Start the camera to reconnect.");};
    socket.onerror=()=>{if(generation===state.generation)stopSession("Could not connect to the local detector.");};
  } catch(error) {
    if(generation!==state.generation)return;
    const message=error.name==="NotAllowedError"?"Camera permission was declined. Allow this page to use your camera, then try again.":error.name==="NotReadableError"?"Your camera may be in use by another app. Close its camera and try again.":error.name==="NotFoundError"?"No camera was found on this device.":error.message;
    stopSession(message);
  }
}
function capture() {
  const video=$("camera");if(!video.videoWidth||!state.stream)throw Error("The camera is not ready.");
  const scale=Math.min(640/video.videoWidth,480/video.videoHeight,1);
  canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);
  ctx.drawImage(video,0,0,canvas.width,canvas.height);
}
function sendFrame(generation) {
  if(generation!==state.generation||!state.running||state.demo||state.inFlight||state.socket?.readyState!==WebSocket.OPEN)return;
  try{capture();}catch(error){stopSession(error.message);return;}
  state.inFlight=true;
  canvas.toBlob(blob=>{
    if(generation!==state.generation||!state.running)return;
    if(!blob||state.socket?.readyState!==WebSocket.OPEN){stopSession("Camera frame could not be sent.");return;}
    state.socket.send(blob);
    state.watchdog=setTimeout(()=>stopSession("The detector stopped responding. Restart the camera."),15000);
  },"image/jpeg",.75);
}
function startDemo() {
  stopSession();notice();prepareSession(true);$("tracking-status").textContent="Simulated cues · camera stays off";
  $("demo-scene").classList.add("resting");
  let tick=0;
  state.demoTimer=setInterval(()=>{
    tick++;$("demo-scene").classList.toggle("resting",tick%2===0);
    if(tick%2&&!state.paused&&enabled().includes("chin_touch"))addEvent("chin_touch","Notice your hand near your chin or beard.","preview");
  },4500);
}
function providerLabel() {return {gemini:"Gemini",openai:"OpenAI",anthropic:"Anthropic"}[$("provider").value];}
function updateProvider(resetAuth=true) {
  const config=state.providerConfig?.providers[$("provider").value];if(!config)return;
  if(resetAuth){$("auth").replaceChildren(...config.auth_modes.map(mode=>new Option({api_key:"API key",vertex_adc:"Vertex ADC",vertex_api_key:"Vertex API key"}[mode],mode)));}
  $("model").value=config.models[$("auth").value]||config.models.api_key;
  $("review-button").querySelector(".button-label").textContent=`Ask ${providerLabel()}`;
  // Changing destination always requires a fresh, explicit choice to share.
  $("cloud-consent").checked=false;$("cloud-result").textContent="Off until you choose to share.";refreshReview();
}
async function review() {
  if($("review-button").disabled)return;
  state.reviewing=true;refreshReview();const generation=state.generation;
  const provider=$("provider").value,auth=$("auth").value,model=$("model").value,conditions=enabled();
  $("cloud-result").textContent="Capturing three snapshots, one second apart…";
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),30000);
  try{
    const frames=[];
    for(let i=0;i<3;i++){
      if(generation!==state.generation||!$("cloud-consent").checked||provider!==$("provider").value||auth!==$("auth").value)throw Error("Cloud review canceled.");
      capture();frames.push(canvas.toDataURL("image/jpeg",.7).split(",")[1]);
      if(i<2)await new Promise(resolve=>setTimeout(resolve,1000));
    }
    $("cloud-result").textContent=`Asking ${providerLabel()}…`;
    const response=await fetch("/api/review",{method:"POST",headers:{"Content-Type":"application/json"},signal:controller.signal,
      body:JSON.stringify({provider,auth,model,consent:true,frames,enabled:conditions})});
    const result=await response.json();if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Check the provider, model, and authentication settings.");
    if(generation!==state.generation||!$("cloud-consent").checked||provider!==$("provider").value||auth!==$("auth").value)return;
    $("cloud-result").textContent=result.note||"Review complete.";
    for(const observation of result.observations){if(observation.confidence>=.7&&!state.paused&&enabled().includes(observation.condition))addEvent(observation.condition,observation.cue,provider);}
  }catch(error){if(generation===state.generation)$("cloud-result").textContent=error.name==="AbortError"?"Review timed out. Local coaching continues.":error.message;}
  finally{clearTimeout(timeout);if(generation===state.generation){state.reviewing=false;refreshReview();}}
}
function download(name,contents,type="application/json") {
  const url=URL.createObjectURL(new Blob([contents],{type}));const link=document.createElement("a");link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$("start-button").onclick=startCamera;$("demo-button").onclick=startDemo;$("stop-button").onclick=()=>stopSession();
$("pause-button").onclick=()=>{state.paused=!state.paused;$("pause-button").querySelector(".button-label").textContent=state.paused?"Resume cues":"Pause cues";syncSettings();};
$("recalibrate-button").onclick=()=>{state.features=[];clearCue();if(state.socket?.readyState===WebSocket.OPEN)state.socket.send(JSON.stringify({type:"calibrate"}));};
$("focus-button").onclick=()=>document.body.classList.toggle("focus-mode");
document.querySelectorAll('[data-condition],#sensitivity,#hold-seconds,#cooldown-seconds,[name="cue-style"]').forEach(el=>el.addEventListener("input",syncSettings));
$("provider").onchange=()=>updateProvider();$("auth").onchange=()=>updateProvider(false);
$("cloud-consent").onchange=()=>{$("cloud-result").textContent=$("cloud-consent").checked?"Ready when you click Ask. No automatic uploads.":"Off until you choose to share.";refreshReview();};
$("review-button").onclick=review;
$("export-summary").onclick=()=>download("miyagi-session.json",JSON.stringify({version:1,simulated:state.demo,events:state.events},null,2));
$("export-window").onclick=()=>{
  const group=$("participant-id").value.trim();
  if(!group){notice("Enter an anonymous participant ID before exporting a training window.");return;}
  if(state.demo||state.features.length<16){notice("Start the real camera and keep your face visible for at least 16 tracked samples first.");return;}
  download(`miyagi-window-${Date.now()}.jsonl`,JSON.stringify({version:1,group,label:$("training-label").value,features:state.features})+"\n","application/x-ndjson");notice("Labeled features exported. No camera images were included.");
};
$("guide-button").onclick=()=>$("guide").showModal();$("close-guide").onclick=()=>$("guide").close();
window.addEventListener("pagehide",()=>stopSession());
document.addEventListener("visibilitychange",()=>{if(document.hidden)state.features=[];});
fetch("/api/status").then(r=>{if(!r.ok)throw Error();return r.json();}).then(status=>{
  state.providerConfig=status.cloud;$("provider").value=status.cloud.provider;updateProvider();
  if([...$("auth").options].some(o=>o.value===status.cloud.auth)){$("auth").value=status.cloud.auth;updateProvider(false);}
  $("detector-label").textContent=status.detector;
  if(!status.local_ready)notice("Camera models are not installed yet. Run uv run miyagi download-models. Cue preview is available now.");
}).catch(()=>notice("Could not reach the Python server. Run uv run miyagi serve and reload this page."));
