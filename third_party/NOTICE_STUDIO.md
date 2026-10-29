AKIRA Studio includes dynamically linked Qt for Python / PySide6 6.8.3
(LGPL-3.0, with corresponding Qt module terms), Rajdhani (SIL OFL 1.1),
OpenAI CLIP with the Xenova ONNX conversion (MIT), ONNX Runtime (MIT),
Hugging Face Tokenizers (Apache-2.0), and imageio-ffmpeg (BSD-2-Clause wrapper).
The FFmpeg executable has its own license: the exact build's `ffmpeg -L`
output and the installed distributions' notices are collected in `packages`.
The native package keeps Qt shared libraries separate and replaceable.

Upstream corresponding sources and licenses:
- https://github.com/pyside/pyside-setup/tree/v6.8.3
- https://github.com/qt/qtbase/tree/v6.8.3
- https://github.com/openai/CLIP
- https://huggingface.co/Xenova/clip-vit-base-patch32/tree/6ef1ebc8b0766a7a8d11b146462c99cdf74dd22d
- https://github.com/google/fonts/tree/main/ofl/rajdhani
- https://github.com/imageio/imageio-ffmpeg
- https://ffmpeg.org/download.html

No license in this directory changes the ownership of the user's imported
fonts, wallpapers or sprites. Their files are kept in the user's data folder.

The included text model is Google Gemma 4 E2B IT (Apache-2.0),
converted by Unsloth to GGUF Q4_K_M (Apache-2.0). It was not trained by Akira.
- https://huggingface.co/google/gemma-4-E2B-it
- https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/tree/0314792d7f1f7e229411f620751375812bb9faf2
See bundled_model.py for the pinned revision, size and SHA-256.
See APACHE2_MODEL_LICENSE.txt for the full license.
