+ Putting @w1.clip_type:qwen_imagex in the config, it takes it but CpmfyUI doesn't complain -- so it seems the setting is ignored.

Quick summary of roles in a Flux workflowclip_l + t5xxl → together encode your prompt (CLIP for style/keywords, T5 for deep understanding).
Main UNET (e.g. flux1-dev-fp16.safetensors) → does the actual image generation.
VAE → turns the generated latent into a real image.

In ComfyUI you’ll usually see nodes like:DualCLIPLoader (or CLIPTextEncodeFlux) → loads clip_l and t5xxl
VAELoader → loads the VAE (flux-vae-bf16 or ae)

Best options for FLUX.2 on Mac right nowRecommended for most Mac users: Full FP16/BF16 FLUX.2-devMain model: flux2-dev.safetensors (the original full-precision version from Black Forest Labs — it's FP16/BF16 in practice).
Download here: https://huggingface.co/black-forest-labs/FLUX.2-dev (you'll need to accept the license/terms first).
Text encoder: mistral_3_small_flux2_bf16.safetensors (BF16 version is available and preferred).
VAE: flux2-vae.safetensors

If you want to stick with the Comfy-Org split files (easier folders):Use the BF16 text encoder (mistral_3_small_flux2_bf16.safetensors) instead of the fp8 one.
For the main model, you may still need to force casting or try community-converted FP16 versions if available. Many Mac users end up using the official full flux2-dev.safetensors.

How to set it up in ComfyUIPut the main model in models/diffusion_models/
Text encoder in models/text_encoders/
VAE in models/vae/
In the UNET Loader node: select the new 16-bit model and set weight_dtype / dtype to default, fp16, or bf16.
Use a Flux.2 example workflow (ComfyUI has official ones).

