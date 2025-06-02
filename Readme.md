# About

This project uses a local llm vision network (in default setting, gemma3 4b) 
and automatically tags a folder structure with jpg files from the network.

You can customize the prompt to generate keywords in your language.

# Synology Photos integration
Disclaimer: Neither this project nor the developer is associated in any kind with Synology.

Since Synology Photos obeys exif/iptc keywords, it's possible to run this script and get automatically clustered tags inside Synology Photos. You can also search by the tags.

## Requirements
A Synology nas with docker support, a x86 CPU and (in case of running the network on the cluster) at least 8+ GB of memory.

1. Install Container Manager from the Package Center
2. Go to project -> Create, choose "Upload docker-compose.yml" and upload the docker-compose.yml inside this project
3. Careful: Check the mount path `- [PATH]:/mnt/images` and set it to a path where your images are located on the nas
   - we strongly recommend to test it in a small sub-folder first
4. Deploy the stack
5. Wait until ollama has downloaded the model and watch the logs of the `app` container

