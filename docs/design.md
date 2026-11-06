# Design system and mascot

The interface follows Material 3 Expressive-inspired hierarchy, tonal surfaces, rounded shapes, segmented selection, state layers, and accessible control sizes. It uses blue as the primary action color, with restrained Google green/yellow/red accents for supporting surfaces and alert states. This is an independent Miyagi application, not a Google product or Google-certified UI.

Google Sans Flex and Material Symbols Rounded are self-hosted. The checked-in Latin font subset supports the English interface; other scripts fall back to the system font. The original logo and companion are replaced by a single generated transparent mascot asset. The application never requests Google Fonts at runtime.

## Sources

- [Material 3 Expressive](https://m3.material.io/blog/building-with-m3-expressive)
- [Material typography](https://m3.material.io/styles/typography/applying-type)
- [Google Sans Flex design and open-source release](https://design.google/library/google-sans-flex-font)
- [Material Symbols usage and self-hosting](https://developers.google.com/fonts/docs/material_symbols)
- [Google Sans Flex source and OFL license](https://github.com/google/fonts/tree/main/ofl/googlesansflex)

Font and icon licenses are copied beside the assets. To refresh these assets deliberately:

```sh
uv run python scripts/download_design_assets.py
```

## Mascot generation

Generated with the built-in image-generation tool on 2026-11-06. No API-key CLI fallback was used. The source artwork is `miyagi/static/miyagi-mascot.png`, 1254×1254 RGBA with transparency. The same asset is used in the application header, favicon, welcome screen, and animated alert companion. It is original artwork and does not use the Google/Gmail mark.

### Final prompt

Use case: logo-brand. Create one original, fun, charming application mascot icon for Miyagi, a private AI meeting coach focused on noticing chin/beard touching. A friendly little wise bearded coach, a rounded head with a bald crown, expressive raised eyebrows, a fluffy white beard, a small warm smile, and simple blue rounded clothing, one small hand resting thoughtfully under the beard. The character feels encouraging and lightly mischievous, never judgmental. Modern Google Material 3 Expressive-compatible illustration: bold clean rounded silhouettes, flat vector-like color shapes with extremely subtle dimensional shading, crisp simple features that read at 32px and 64px. Primary cobalt/Google blue with warm peach skin, white beard, dark navy details, a tiny warm yellow accent. Centered close-up head-and-shoulders avatar, fills 88% of a square composition. Transparent background, no surrounding badge, no scenery, no words, no letters, no logo text, no watermark. This must be an original character, not the Google logo or Gmail envelope. Deliver a single polished square icon/mascot with genuinely transparent pixels around its silhouette.
