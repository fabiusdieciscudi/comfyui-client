+ Capability to set title and description that will be later used by set-metadata
+ Idem for colours
+ --config shortcut for the model configuration
  + submit command: add a --model option that works as a shortcut for a model config; that is, --model foobar is the same of --prompt-file prompts/configs/[wf]-foobar.txt. It must use the same relative path resolving used by --w1. Note that [wf] must be resolved with the workflow name (w1 for --w1), so this arg can be only used if --w1 has been previously passed.
+ Embed configs and workflows
+ Document --output
+ Default di upscaling nei config
+ W1 API manually patched for disconnected w,h nodes, not in sync with master workflow
+ nearest-exact in Upscale image -> parameterize it.
+ tag regex should go into an external config file.
+ Add @keyword, @title, @description
+ Document which node packs W1 requires
+ Actually SubmitCommand sets the title and description, only if the image is downloaded; instead it must set them to special nodes in the workflow, and delegate the operation to set-metadata;
+ for sure, if the image is downloaded, it could call set-metadata on it, but I'd do this later, in a separate issue.
+ Add a warning if the number of tokens (computed from words in the prompt) is > the maximum suggested for a given model.
+ Check matching defaults between JSON and PY.