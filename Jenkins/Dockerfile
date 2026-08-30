FROM jenkins/jenkins:lts-jdk17

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL --proto '=https' --tlsv1.2 https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

ARG KUBECTL_VERSION=v1.31.2
RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) kubectl_sha256='399e9d1995da80b64d2ef3606c1a239018660d8b35209fba3f7b0bc11c631c68' ;; \
      arm64) kubectl_sha256='bb9fd6e5a92c2e2378954a2f1a8b4ccb2e8ba5a3635f870c3f306a53b359f971' ;; \
      *) echo "Arquitectura no soportada: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --proto '=https' --tlsv1.2 -o /usr/local/bin/kubectl \
      "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl"; \
    echo "${kubectl_sha256}  /usr/local/bin/kubectl" | sha256sum -c -; \
    chmod +x /usr/local/bin/kubectl

ARG HELM_VERSION=v3.16.4
RUN set -eu; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) helm_sha256='fc307327959aa38ed8f9f7e66d45492bb022a66c3e5da6063958254b9767d179' ;; \
      arm64) helm_sha256='d3f8f15b3d9ec8c8678fbf3280c3e5902efabe5912e2f9fcf29107efbc8ead69' ;; \
      *) echo "Arquitectura no soportada: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --proto '=https' --tlsv1.2 -o /tmp/helm.tar.gz \
      "https://get.helm.sh/helm-${HELM_VERSION}-linux-${arch}.tar.gz"; \
    echo "${helm_sha256}  /tmp/helm.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/helm.tar.gz -C /tmp; \
    mv "/tmp/linux-${arch}/helm" /usr/local/bin/helm; \
    rm -rf /tmp/helm.tar.gz "/tmp/linux-${arch}"

USER jenkins

RUN jenkins-plugin-cli --plugins \
      docker-workflow \
      git \
      credentials-binding \
      pipeline-utility-steps \
      workflow-aggregator
