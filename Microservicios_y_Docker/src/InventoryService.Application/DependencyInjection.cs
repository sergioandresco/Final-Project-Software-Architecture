using InventoryService.Application.Products;
using Microsoft.Extensions.DependencyInjection;

namespace InventoryService.Application;

/// <summary>
/// Registro de los servicios de la capa Application (casos de uso).
/// </summary>
public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddScoped<IProductService, ProductService>();
        return services;
    }
}
