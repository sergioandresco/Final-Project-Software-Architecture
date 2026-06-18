using InventoryService.Api.Middleware;
using InventoryService.Application;
using InventoryService.Infrastructure;
using InventoryService.Infrastructure.Persistence;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;

var builder = WebApplication.CreateBuilder(args);

// --- Servicios ---
builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
{
    options.SwaggerDoc("v1", new Microsoft.OpenApi.Models.OpenApiInfo
    {
        Title = "Inventory Service API",
        Version = "v1",
        Description = "Microservicio de gestión de inventario (CRUD de productos)."
    });
});

// Composición de capas (regla de dependencia hacia adentro)
builder.Services.AddApplication();                       // casos de uso
builder.Services.AddInfrastructure(builder.Configuration); // persistencia (EF Core + SQLite)

// Health checks: 'live' (¿está vivo el proceso?) y 'ready' (¿puede atender, incluida la BD?)
builder.Services.AddHealthChecks()
    .AddDbContextCheck<InventoryDbContext>(name: "database", tags: new[] { "ready" });

var app = builder.Build();

// --- Inicialización de la base de datos ---
// Para aprendizaje usamos EnsureCreated (crea el esquema si no existe).
// En producción se recomienda usar migraciones EF Core: db.Database.Migrate().
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<InventoryDbContext>();
    db.Database.EnsureCreated();
}

// --- Pipeline HTTP ---
// Manejo centralizado de excepciones -> ProblemDetails.
app.UseMiddleware<ExceptionHandlingMiddleware>();

app.UseSwagger();
app.UseSwaggerUI();

app.MapControllers();

// Endpoints de salud para sondas de Kubernetes (liveness / readiness)
app.MapHealthChecks("/health/live", new HealthCheckOptions
{
    Predicate = _ => false // sin checks: solo confirma que el proceso responde
});
app.MapHealthChecks("/health/ready", new HealthCheckOptions
{
    Predicate = check => check.Tags.Contains("ready")
});

app.Run();
