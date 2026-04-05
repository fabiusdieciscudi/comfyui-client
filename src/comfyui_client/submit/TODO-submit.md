+ @title non filtrato bene nel prompt se c'è uno spazio
+ Sbarazzarsi di merger_node_id

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