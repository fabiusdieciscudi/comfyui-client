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
Z_IMAGE_T	:= --workflow $(W1) --prompt-file $(CONFIGS)/w1-z_image_turbo_bf16.txt

OPTIONS		:= $(OPTIONS) --no-wait

ifeq ($(filter fast,$(MAKECMDGOALS)),fast)
OPTIONS 	:= $(OPTIONS) --range w1.steps=2 --scale 0.5
endif

ifeq ($(filter dry-run,$(MAKECMDGOALS)),dry-run)
OPTIONS		:= $(OPTIONS) --dry-run
endif


all: cat

clean:
	rm -rf $(BUILD)

build:
	mkdir -p $(BUILD)

output: build
	mkdir -p $(OUTPUT)

cat: output
	$(CLIENT) $(Z_IMAGE_T) --prompt "A cat" $(OPTIONS)

prompt:
	$(CLIENT) $(Z_IMAGE_T) --prompt "$(PROMPT)" $(OPTIONS)

include Makefile-py
