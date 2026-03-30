# SPDX-FileCopyrightText: © 2026-present Fabius Dieciscudi
# SPDX-License-Identifier: MIT

SHELL 		:= bash
VENV  		:= .venv

BUILD		:= build
OUTPUT		:= $(BUILD)/output

CONFIGS 	:= prompts/configs/
WORKFLOWS	:= workflows/api
W1			:= $(WORKFLOWS)/'W1 (diffusion based).json'

CLIENT		:= ./ComfyUIClient
Z_IMAGE_T	:= --w1 --prompt-file $(CONFIGS)/w1-z_image_turbo_bf16.txt

ifeq ($(filter fast,$(MAKECMDGOALS)),fast)
OPTIONS 	:= $(OPTIONS) --range w1.steps=2 --range w1.up_steps=2
endif

ifeq ($(filter small,$(MAKECMDGOALS)),small)
OPTIONS 	:= $(OPTIONS) --scale 0.5
endif

ifeq ($(filter dry-run,$(MAKECMDGOALS)),dry-run)
OPTIONS		:= $(OPTIONS) --dry-run
endif

ifeq ($(filter wait,$(MAKECMDGOALS)),wait)
OPTIONS		:= $(OPTIONS) wait
endif

.PHONY: al cat clean build output prompt cat moonlight small fast dry-run no-wait

all: cat

clean:
	@rm -rfv $(BUILD)

build:
	@mkdir -pv $(BUILD)

output: build
	@mkdir -pv $(OUTPUT)

prompt: output
	$(CLIENT) submit $(Z_IMAGE_T) --prompt "$(PROMPT)" $(OPTIONS) --output $(OUTPUT)

cat: output
	$(CLIENT) submit $(Z_IMAGE_T) --prompt "A cat sitting on a sofa, smoking a pipe" $(OPTIONS) --output $(OUTPUT)

cat-upscale: output
	$(CLIENT) submit $(Z_IMAGE_T) --prompt "A cat sitting on a sofa, smoking a pipe" $(OPTIONS) --output $(OUTPUT) --upscale 4k

moonlight: output
	$(CLIENT) submit $(Z_IMAGE_T) --prompt-file prompts/moonlight.txt $(OPTIONS) --output $(OUTPUT)

small fast dry-run:
	@true

include Makefile-py
