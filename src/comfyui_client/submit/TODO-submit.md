 Putting @w1.clip_type:qwen_imagex in the config, it takes it but CpmfyUI doesn't complain -- so it seems the setting is ignored.
+ w1.up_width_present = true sbagliato

+ Embed configs and workflows
+ W1 API manually patched for disconnected w,h nodes, not in sync with master workflow
+ tag regex should go into an external config file.
+ for sure, if the image is downloaded, submit could call set-metadata on it, but I'd do this later, in a separate issue.
+ Check matching defaults between JSON and PY.
+ Document --model
+ lora syntax doesn't work with multiple items on the same line
+ lora syntax doesn't work with third argument
+ Perhaps there's a difference now that CLIP is post-processed by LOras?
+ Ci sono 2 NODI SPURI AGGIUNTIVI Tag: w1.lora_name_04
+ Default lora_strength must be 0.0
+ With <lora:> syntax, duplicated LOras should override settings, not be really duplicated.
+ Document which node packs W1 requires
+ Make --debug to work, add --verbose with info()
    
TO CHECK
+ Document --output
+ FORSE FATTO: @title non filtrato bene nel prompt se c'è uno spazio
+ nearest-exact in Upscale image -> parameterize it.
+ Default di upscaling nei config
+ Stop if > 4 LOras
+ Add a warning if the number of tokens (computed from words in the prompt) is > the maximum suggested for a given model.
