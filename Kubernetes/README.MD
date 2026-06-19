# Despliegue de Microservicio Inventory Service en Kubernetes con K3d

---

# Objetivo

Desplegar un microservicio basado en Docker dentro de un clúster Kubernetes local utilizando K3d, validando la ejecución de Pods, Deployments y Services, así como la exposición de la aplicación mediante port-forwarding.

---

# Arquitectura Implementada

```text
Docker Image
      │
      ▼
Kubernetes Deployment
      │
      ▼
Pod
      │
      ▼
Service (ClusterIP)
      │
      ▼
Port Forward
      │
      ▼
Swagger UI
```

---

# Tecnologías Utilizadas

| Tecnología       | Versión              |
| ---------------- | -------------------- |
| Docker Desktop   | 4.77.0               |
| Docker Engine    | 29.5.3               |
| Kubernetes (k3s) | v1.35.5+k3s1         |
| k3d              | v5.9.0               |
| kubectl          | v1.34.1              |
| ASP.NET Core     | .NET 8               |
| Docker Hub       | Registro de imágenes |

---

# Instalación de Herramientas

## Verificación de Docker

```powershell
docker version
```

Resultado esperado:

```text
Client:
 Version: 29.5.3

Server:
 Docker Desktop 4.77.0
```

---

## Instalación de K3d

Instalar mediante Chocolatey:

```powershell
choco install k3d -y
```

Verificar instalación:

```powershell
k3d version
```

Resultado:

```text
k3d version v5.9.0
k3s version v1.35.5-k3s1
```

---

## Verificación de kubectl

```powershell
kubectl version --client
```

Resultado:

```text
Client Version: v1.34.1
```

---

# Creación del Clúster Kubernetes

Crear el clúster:

```powershell
k3d cluster create mi-cluster
```

Verificar:

```powershell
k3d cluster list
```

Resultado:

```text
NAME         SERVERS   AGENTS
mi-cluster   1/1       0/0
```

---

# Corrección del Kubeconfig

Inicialmente el clúster generó una configuración utilizando:

```text
host.docker.internal
```

lo que impedía la conexión desde Windows.

Se modificó el archivo:

```text
C:\Users\marip\.kube\config
```

reemplazando:

```yaml
server: https://host.docker.internal:6443
```

por:

```yaml
server: https://127.0.0.1:6443
```

Posteriormente se verificó la conectividad.

---

# Validación del Clúster

Comando:

```powershell
kubectl get nodes
```

Resultado:

```text
NAME                      STATUS   ROLES
k3d-mi-cluster-server-0   Ready    control-plane
```

Esto confirma que el nodo principal del clúster se encuentra operativo.

---

# Despliegue de Aplicación de Prueba (Nginx)

Se desplegó inicialmente Nginx para validar el correcto funcionamiento del clúster.

## Deployment

```powershell
kubectl create deployment nginx --image=nginx
```

## Service

```powershell
kubectl expose deployment nginx --type=NodePort --port=80
```

Validación:

```powershell
kubectl get pods
kubectl get svc
```

---

# Imagen Docker del Proyecto

El equipo suministró la siguiente imagen Docker:

```text
davidvasbe/inventory-service:1.0.0
```

Prueba local:

```powershell
docker pull davidvasbe/inventory-service:1.0.0
```

Ejecución:

```powershell
docker run -d -p 8080:8080 -v inventory-data:/data davidvasbe/inventory-service:1.0.0
```

Validación:

```text
http://localhost:8080/swagger
```

Se confirmó la correcta ejecución mediante Swagger UI.

---

# Despliegue del Microservicio en Kubernetes

## Deployment

Archivo:

inventory-deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service

spec:
  replicas: 1

  selector:
    matchLabels:
      app: inventory-service

  template:
    metadata:
      labels:
        app: inventory-service

    spec:
      containers:
      - name: inventory-service
        image: davidvasbe/inventory-service:1.0.0

        ports:
        - containerPort: 8080

        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 15

        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 15
```

Aplicación:

```powershell
kubectl apply -f inventory-deployment.yaml
```

---

## Service

Archivo:

inventory-service.yaml

```yaml
apiVersion: v1
kind: Service

metadata:
  name: inventory-service

spec:
  selector:
    app: inventory-service

  ports:
  - protocol: TCP
    port: 8080
    targetPort: 8080

  type: ClusterIP
```

Aplicación:

```powershell
kubectl apply -f inventory-service.yaml
```

---

# Validación del Despliegue

## Deployments

```powershell
kubectl get deployments
```

Resultado:

```text
NAME                READY
inventory-service   1/1
nginx               1/1
```

---

## Pods

```powershell
kubectl get pods
```

Resultado:

```text
inventory-service-65c589884b-7l84b   1/1 Running
nginx-56c45fd5ff-dq5sg               1/1 Running
```

---

## Services

```powershell
kubectl get svc
```

Resultado:

```text
NAME                TYPE
inventory-service   ClusterIP
kubernetes          ClusterIP
nginx               NodePort
```

---

# Acceso a la Aplicación

Como el Service fue configurado como ClusterIP, se utilizó Port Forwarding.

```powershell
kubectl port-forward service/inventory-service 8080:8080
```

Acceso:

```text
http://localhost:8080/swagger
```

Resultado:

* Swagger UI accesible.
* API funcional.
* Endpoints disponibles.

---

---

# Resultado Final

Se logró desplegar exitosamente el microservicio Inventory Service dentro de un clúster Kubernetes local basado en K3d.

El despliegue incluyó:

* Creación del clúster Kubernetes.
* Configuración de kubectl.
* Despliegue de imágenes Docker.
* Creación de Deployments.
* Creación de Services.
* Configuración de Health Checks.
* Validación mediante Swagger UI.
* Verificación de Pods y Servicios activos.

Estado final:

```text
Cluster Kubernetes: Operativo
Deployment: Operativo
Pod: Running
Service: Operativo
Swagger: Disponible
Health Checks: Correctos
```

Proyecto desplegado exitosamente sobre Kubernetes.
