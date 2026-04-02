+ Capability to set title and description that will be later used by set-metadata
+ Idem for colours
+ --config shortcut for the model configuration
  + submit command: add a --model option that works as a shortcut for a model config; that is, --model foobar is the same of --prompt-file prompts/configs/[wf]-foobar.txt. It must use the same relative path resolving used by --w1. Note that [wf] must be resolved with the workflow name (w1 for --w1), so this arg can be only used if --w1 has been previously passed.
+ Embed configs and worflows
+ Translate code in regular objects