# Jenkins (pipeline de CD)

Este Jenkins ejecuta el [`Jenkinsfile`](../Jenkinsfile) de la raíz del repositorio:
construye la imagen Docker del microservicio, la publica en Docker Hub y despliega
la nueva versión en el clúster k3d vía Helm. La CI (build/test/SonarCloud/Snyk) vive
en GitHub Actions (`.github/workflows/ci.yml`).

## 1. Levantar Jenkins

```bash
cd Jenkins
docker compose up -d --build
```

Abre <http://localhost:8090>. La primera vez pedirá una contraseña de administrador:

```bash
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Instala los plugins sugeridos (los específicos del pipeline ya vienen preinstalados
en la imagen, ver [`Dockerfile`](./Dockerfile)) y crea tu usuario admin.

## 2. Crear el Pipeline job

1. **New Item → Pipeline**, nómbralo p. ej. `inventory-service-cd`.
2. En **Pipeline → Definition**, elige **Pipeline script from SCM**.
3. **SCM: Git**, URL del repo:
   `https://github.com/sergioandresco/Final-Project-Software-Architecture.git`
4. **Branch**: `*/main` (o la rama que quieras desplegar).
5. **Script Path**: `Jenkinsfile` (ya es el valor por defecto).

## 3. Credenciales requeridas

En **Manage Jenkins → Credentials → System → Global credentials**, crea:

| ID                     | Tipo                       | Valor                                                                 |
| ---------------------- | --------------------------- | ---------------------------------------------------------------------- |
| `dockerhub-credentials` | Username with password      | Tu usuario de Docker Hub y un [access token](https://hub.docker.com/settings/security) (mismos valores que usas hoy en los secrets `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` de GitHub Actions) |
| `k3d-kubeconfig`        | Secret file                 | El kubeconfig de tu clúster k3d (ver paso 4)                          |

## 4. Kubeconfig para el clúster k3d

Exporta el kubeconfig del clúster:

```bash
k3d kubeconfig get arquitectura > k3d-kubeconfig.yaml
```

**Importante (Docker Desktop en macOS):** ese archivo apunta al API server como
`https://0.0.0.0:<puerto>` o `127.0.0.1`, que dentro del contenedor de Jenkins
se refiere al propio contenedor, no al host. Reemplaza el host por
`host.docker.internal` antes de subirlo como credencial:

```bash
sed -i '' 's/0\.0\.0\.0/host.docker.internal/; s/127\.0\.0\.1/host.docker.internal/' k3d-kubeconfig.yaml
```

Sube `k3d-kubeconfig.yaml` como el valor de la credencial `k3d-kubeconfig`
(tipo **Secret file**). El Jenkinsfile lo expone automáticamente como la
variable de entorno `KUBECONFIG` en la etapa de despliegue.

## 5. Ejecutar

**Build Now** en el job. Las etapas: `Checkout → Build & Test (.NET) → Docker Build →
Docker Push → Deploy to k3d`.
