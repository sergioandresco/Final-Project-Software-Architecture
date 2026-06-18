# Inventory Service — Microservicio de inventario en .NET 8

Microservicio CRUD para gestionar un inventario de productos. Construido con **ASP.NET Core 8**, **Entity Framework Core** y **SQLite**, organizado en capas y listo para contenerizar con Docker y, más adelante, desplegar en Kubernetes.

---

## 1. Arquitectura limpia por capas

El proyecto sigue **Clean Architecture**: la regla de dependencia apunta siempre **hacia adentro**. Las capas externas conocen a las internas, nunca al revés.

```
   Api  ──►  Infrastructure ──►  Application  ──►  Domain
(presentación)   (EF Core)        (casos de uso)   (entidades)
```

| Capa            | Responsabilidad                                          | Depende de        |
|-----------------|----------------------------------------------------------|-------------------|
| **Domain**      | Entidades del negocio. Sin dependencias externas.        | — (núcleo)        |
| **Application** | Casos de uso, DTOs, puertos (interfaces), excepciones.   | Domain            |
| **Infrastructure** | Implementa los puertos: EF Core, SQLite, repositorios. | Application, Domain |
| **Api**         | Controladores, middleware, Swagger, composición (DI).    | Application, Infrastructure |

```
Microservicios y Docker/
├── InventoryService.sln
├── Dockerfile                       # Imagen multi-stage del microservicio
├── docker-compose.yml               # Ejecución local con volumen persistente
├── .dockerignore
├── .gitignore
├── README.md
└── src/
    ├── InventoryService.Domain/             # Núcleo: entidades
    │   └── Entities/Product.cs
    ├── InventoryService.Application/        # Casos de uso + contratos
    │   ├── Common/Exceptions/               #   NotFoundException, ConflictException
    │   ├── Products/
    │   │   ├── Dtos/ProductDtos.cs
    │   │   ├── IProductRepository.cs        #   puerto (lo implementa Infrastructure)
    │   │   ├── IProductService.cs
    │   │   └── ProductService.cs            #   lógica de aplicación
    │   └── DependencyInjection.cs           #   AddApplication()
    ├── InventoryService.Infrastructure/     # Detalles técnicos (persistencia)
    │   ├── Persistence/InventoryDbContext.cs
    │   ├── Persistence/Repositories/ProductRepository.cs
    │   └── DependencyInjection.cs           #   AddInfrastructure()
    └── InventoryService.Api/                # Presentación (HTTP)
        ├── Controllers/ProductsController.cs    # controlador delgado
        ├── Middleware/ExceptionHandlingMiddleware.cs
        ├── Program.cs                           # raíz de composición
        └── appsettings.json
```

**Beneficios:** el dominio y los casos de uso son independientes de EF Core o de ASP.NET; se pueden probar de forma aislada y cambiar la base de datos o el framework web sin tocar la lógica de negocio. El controlador es delgado: solo recibe la petición y delega en `IProductService`; los errores de negocio (no encontrado, conflicto) se traducen a HTTP de forma centralizada en un middleware.

---

## 2. API disponible

| Método | Ruta                     | Descripción                  |
|--------|--------------------------|------------------------------|
| GET    | `/api/products`          | Lista todos los productos    |
| GET    | `/api/products/{id}`     | Obtiene un producto por id   |
| POST   | `/api/products`          | Crea un producto             |
| PUT    | `/api/products/{id}`     | Actualiza un producto        |
| DELETE | `/api/products/{id}`     | Elimina un producto          |
| GET    | `/health/live`           | Liveness probe (Kubernetes)  |
| GET    | `/health/ready`          | Readiness probe (incluye BD) |
| GET    | `/swagger`               | Documentación interactiva    |

---

