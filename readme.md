# Inventory Service - Arquitectura de Microservicios con Docker, Kubernetes, Helm, GitHub Actions y ArgoCD

## Descripción General

Este proyecto implementa un microservicio de inventario desarrollado en **.NET 8**, siguiendo principios de **Clean Architecture**, empaquetado mediante **Docker**, desplegado sobre **Kubernetes (k3d)** y administrado utilizando **Helm** y **ArgoCD** bajo una estrategia **GitOps**.

Además, se implementó una estrategia de **Integración Continua (CI)** utilizando **GitHub Actions**, con pipelines independientes para los ambientes de desarrollo y producción.

---

# Arquitectura General de la Solución

```text
┌─────────────────────┐
│     GitHub Repo     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  GitHub Actions CI  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     Docker Hub      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│      ArgoCD         │
│   GitOps Engine     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│        Helm         │
│ Package Management  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    Kubernetes       │
│       (k3d)         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Inventory Service   │
└─────────────────────┘
```

---

# Tecnologías Utilizadas

| Tecnología            | Propósito                    |
| --------------------- | ---------------------------- |
| ASP.NET Core 8        | Desarrollo del microservicio |
| Entity Framework Core | Persistencia                 |
| SQLite                | Base de datos                |
| Docker                | Contenerización              |
| Docker Hub            | Registro de imágenes         |
| Kubernetes            | Orquestación                 |
| k3d                   | Kubernetes local             |
| Helm                  | Gestión de paquetes          |
| ArgoCD                | GitOps                       |
| GitHub Actions        | Integración Continua         |
| Swagger               | Documentación API            |

---

# Arquitectura Limpia (Clean Architecture)

El proyecto sigue los principios de Clean Architecture, donde las dependencias siempre apuntan hacia el núcleo del negocio.

```text
Api  ──► Infrastructure ──► Application ──► Domain
```

| Capa           | Responsabilidad                 |
| -------------- | ------------------------------- |
| Domain         | Entidades de negocio            |
| Application    | Casos de uso, DTOs y contratos  |
| Infrastructure | Persistencia y acceso a datos   |
| Api            | Exposición HTTP y configuración |

## Estructura del Proyecto

```text
InventoryService.sln
├── Dockerfile
├── docker-compose.yml
├── README.md
└── src/
    ├── InventoryService.Domain
    │   └── Entities/Product.cs
    ├── InventoryService.Application
    │   ├── Common/Exceptions
    │   ├── Products
    │   └── DependencyInjection.cs
    ├── InventoryService.Infrastructure
    │   ├── Persistence
    │   └── DependencyInjection.cs
    └── InventoryService.Api
        ├── Controllers
        ├── Middleware
        ├── Program.cs
        └── appsettings.json
```

## Beneficios

* Separación clara de responsabilidades.
* Bajo acoplamiento.
* Alta mantenibilidad.
* Facilidad para pruebas unitarias.
* Independencia de frameworks y tecnologías externas.

---

# APIs Disponibles

| Método | Endpoint           | Descripción                 |
| ------ | ------------------ | --------------------------- |
| GET    | /api/products      | Obtener todos los productos |
| GET    | /api/products/{id} | Obtener producto por ID     |
| POST   | /api/products      | Crear producto              |
| PUT    | /api/products/{id} | Actualizar producto         |
| DELETE | /api/products/{id} | Eliminar producto           |
| GET    | /health/live       | Liveness Probe              |
| GET    | /health/ready      | Readiness Probe             |
| GET    | /swagger           | Documentación Swagger       |

---

# Contenerización con Docker

## Construcción de Imagen

```bash
docker build -t inventory-service:1.0.0 .
```

## Ejecución Local

```bash
docker run -p 8080:8080 inventory-service:1.0.0
```

## Publicación en Docker Hub

```bash
docker tag inventory-service:1.0.0 sergiocosu/inventory-service:1.0.0

docker push sergiocosu/inventory-service:1.0.0
```

Imagen utilizada:

```text
sergiocosu/inventory-service:1.0.0
```

---

# Kubernetes

## Creación del Clúster

```bash
k3d cluster create arquitectura
```

Validar:

```bash
kubectl get nodes
```

## Despliegue Inicial

Aplicar manifiestos Kubernetes:

```bash
kubectl apply -f Kubernetes/
```

Validar:

```bash
kubectl get pods
kubectl get svc
```

## Acceso a la Aplicación

```bash
kubectl port-forward svc/inventory-service 8080:8080
```

Abrir:

```text
http://localhost:8080/swagger
```

---

# Helm

Helm fue utilizado para empaquetar y parametrizar el despliegue Kubernetes.

## Creación del Chart

```bash
helm create inventory-chart
```

Estructura:

```text
inventory-chart/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    └── service.yaml
```

## Configuración de Values

```yaml
app:
  name: inventory-service

replicaCount: 1

image:
  repository: sergiocosu/inventory-service
  tag: 1.0.0

container:
  port: 8080

service:
  type: ClusterIP
  port: 8080

health:
  livenessPath: /health/live
  readinessPath: /health/ready
```

## Instalación

```bash
helm install inventory ./inventory-chart
```

Actualización:

```bash
helm upgrade inventory ./inventory-chart
```

Validar:

```bash
helm list
kubectl get pods
```

---

# Integración Continua con GitHub Actions

Se implementaron dos pipelines independientes para soportar los ambientes de desarrollo y producción.

## Pipeline de Desarrollo

Archivo:

```text
.github/workflows/ci-development.yml
```

### Trigger

```yaml
on:
  push:
    branches: [development]
  pull_request:
    branches: [development]
```

### Funcionalidades

* Checkout del código.
* Configuración de .NET 8.
* Restore de dependencias.
* Build de la solución.
* Ejecución de pruebas.
* Construcción de imagen Docker.
* Publicación de imagen Docker de desarrollo.
* Creación de GitHub Pre-Release.

### Versionamiento

Las imágenes de desarrollo utilizan el SHA del commit:

```text
sergiocosu/inventory-service:dev-a1b2c3d4
```

### Beneficio

Permite validar cambios continuamente sin afectar las versiones estables.

---

## Pipeline de Producción

Archivo:

```text
.github/workflows/cd-main.yml
```

### Trigger

```yaml
on:
  push:
    branches: [main]
```

### Funcionalidades

* Checkout.
* Restore.
* Build.
* Test.
* Generación automática de versión.
* Docker Build.
* Docker Push.
* GitHub Release.

### Versionamiento Automático

Ejemplo:

```text
v1.0.0
v1.0.1
v1.0.2
```

### Imágenes Generadas

```text
sergiocosu/inventory-service:1.0.0
sergiocosu/inventory-service:latest
```

### Beneficio

Garantiza versiones estables y trazables para despliegues productivos.

---

# ArgoCD

## Instalación

Crear namespace:

```bash
kubectl create namespace argocd
```

Instalar:

```bash
kubectl apply -n argocd \
-f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

Validar:

```bash
kubectl get pods -n argocd
```

---

## Acceso

```bash
kubectl port-forward svc/argocd-server \
-n argocd 8081:443
```

URL:

```text
https://localhost:8081
```

Usuario:

```text
admin
```

Contraseña:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
-o jsonpath="{.data.password}" | base64 -d
```

---

# Configuración GitOps

Repositorio:

```text
https://github.com/sergioandresco/Final-Project-Software-Architecture
```

Archivo:

```text
application.yaml
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application

metadata:
  name: inventory
  namespace: argocd

spec:
  project: default

  source:
    repoURL: https://github.com/sergioandresco/Final-Project-Software-Architecture.git
    targetRevision: main
    path: inventory-chart

  destination:
    server: https://kubernetes.default.svc
    namespace: default

  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

Aplicar:

```bash
kubectl apply -f application.yaml
```

---

# Flujo Completo CI/CD + GitOps

```text
Developer
    │
    ▼
development
    │
    ▼
CI Development
    │
    ├── Restore
    ├── Build
    ├── Test
    ├── Docker Build
    ├── Docker Push (dev)
    └── GitHub Pre-Release
    │
    ▼
Pull Request
    │
    ▼
main
    │
    ▼
CI Production
    │
    ├── Restore
    ├── Build
    ├── Test
    ├── Versioning
    ├── Docker Build
    ├── Docker Push
    └── GitHub Release
    │
    ▼
Docker Hub
    │
    ▼
Git Repository
    │
    ▼
ArgoCD
    │
    ▼
Helm
    │
    ▼
Kubernetes (k3d)
    │
    ▼
Inventory Service
```

---

# Validaciones

Verificar Kubernetes:

```bash
kubectl get pods
kubectl get svc
```

Verificar Helm:

```bash
helm list
```

Verificar ArgoCD:

```bash
kubectl get applications -n argocd
```

Resultado esperado:

```text
inventory
Healthy
Synced
```

---

# Conclusión

Se implementó exitosamente una arquitectura moderna basada en microservicios utilizando .NET 8, Docker, Kubernetes, Helm, GitHub Actions y ArgoCD.

La solución permite automatizar el ciclo completo de desarrollo y despliegue mediante Integración Continua y GitOps, garantizando trazabilidad, reproducibilidad, versionamiento automatizado y facilidad de administración de los entornos.
