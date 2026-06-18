using InventoryService.Application.Products;
using InventoryService.Infrastructure.Persistence;
using InventoryService.Infrastructure.Persistence.Repositories;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace InventoryService.Infrastructure;

/// <summary>
/// Registro centralizado de los servicios de infraestructura (persistencia).
/// </summary>
public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // La cadena de conexión se toma de configuración / variables de entorno.
        // Ej. en Docker:  ConnectionStrings__Default=Data Source=/data/inventory.db
        var connectionString = configuration.GetConnectionString("Default")
                               ?? "Data Source=inventory.db";

        services.AddDbContext<InventoryDbContext>(options =>
            options.UseSqlite(connectionString));

        services.AddScoped<IProductRepository, ProductRepository>();

        return services;
    }
}
