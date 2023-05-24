FROM mcr.microsoft.com/devcontainers/python:0-3.11

USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends mininet bridge-utils iputils-ping wget gnupg && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# https://github.com/puppeteer/puppeteer/blob/main/docs/troubleshooting.md#running-puppeteer-in-docker
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | \
    apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable fonts-ipafont-gothic fonts-wqy-zenhei fonts-thai-tlwg fonts-kacst fonts-freefont-ttf libxss1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER vscode
