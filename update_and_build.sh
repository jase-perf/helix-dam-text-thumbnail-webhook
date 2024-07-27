#!/bin/bash
git stash
git pull
git stash pop
docker build -t text-thumbnail-webhook .