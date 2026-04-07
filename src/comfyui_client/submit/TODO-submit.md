+ FORSE FATTO: @title non filtrato bene nel prompt se c'è uno spazio
+ Putting @w1.clip_type:qwen_imagex in the config, it takes it but CpmfyUI doesn't complain -- so it seems the setting is ignored.
+ w1.up_width_present = true sbagliato

+ --config shortcut for the model configuration
  + submit command: add a --model option that works as a shortcut for a model config; that is, --model foobar is the same of --prompt-file prompts/configs/[wf]-foobar.txt. It must use the same relative path resolving used by --w1. Note that [wf] must be resolved with the workflow name (w1 for --w1), so this arg can be only used if --w1 has been previously passed.
+ Embed configs and workflows
+ Document --output
+ Default di upscaling nei config
+ W1 API manually patched for disconnected w,h nodes, not in sync with master workflow
+ nearest-exact in Upscale image -> parameterize it.
+ tag regex should go into an external config file.
+ Document which node packs W1 requires
+ for sure, if the image is downloaded, submit could call set-metadata on it, but I'd do this later, in a separate issue.
+ Add a warning if the number of tokens (computed from words in the prompt) is > the maximum suggested for a given model.
+ Check matching defaults between JSON and PY.
  + Pre-check the model and LoRA names --- e.g. http://localhost:8000/models/loras etc... http://localhost:8188/object_info?node=KSampler
    import requests
  
    response = requests.get("http://localhost:8188/object_info?node=KSampler")
    data = response.json()
  
    samplers = data["KSampler"]["input"]["required"]["sampler_name"][0]
    schedulers = data["KSampler"]["input"]["required"]["scheduler"][0]
  
    print("Sampler disponibili:", samplers)
    print("Scheduler disponibili:", schedulers)
+ Preprocess the standard syntax <lora,strength> to generate @w1.lora_name and @e1.lora_strength
+ Allow multiple LoRAs.