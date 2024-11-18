#!/usr/bin/env bash

mv .git ../.
rm -rf *
rm -rf .*
mv ../.git .
git clone https://github.com/EmbeddedLLM/JAM.ai.dev
rm -rf JAM.ai.dev/.git
rm -rf JAM.ai.dev/.vscode
rm -rf JAM.ai.dev/archive
cp -r JAM.ai.dev/.  .
source scripts/remove_cloud_modules.sh
rm -rf JAM.ai.dev/
sed -i -e 's:JAM.ai.dev:JamAIBase:g' README.md
mv .env.example .env
