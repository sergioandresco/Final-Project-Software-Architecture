using InventoryService.Application.Products.Dtos;

namespace InventoryService.Application.Products;

/// <summary>
/// Casos de uso del inventario. La capa de presentación (API) depende de esta
/// abstracción, no de la implementación concreta.
/// </summary>
public interface IProductService
{
    Task<IReadOnlyList<ProductDto>> GetAllAsync(CancellationToken ct = default);

    /// <summary>Obtiene un producto. Lanza NotFoundException si no existe.</summary>
    Task<ProductDto> GetByIdAsync(Guid id, CancellationToken ct = default);

    /// <summary>Crea un producto. Lanza ConflictException si el SKU ya existe.</summary>
    Task<ProductDto> CreateAsync(CreateProductRequest request, CancellationToken ct = default);

    /// <summary>Actualiza un producto. Lanza NotFoundException si no existe.</summary>
    Task<ProductDto> UpdateAsync(Guid id, UpdateProductRequest request, CancellationToken ct = default);

    /// <summary>Elimina un producto. Lanza NotFoundException si no existe.</summary>
    Task DeleteAsync(Guid id, CancellationToken ct = default);

    /// <summary>
    /// Ajusta la cantidad en inventario sumando/restando <see cref="AdjustStockRequest.Delta"/>.
    /// Lanza NotFoundException si no existe y ConflictException si el resultado quedaría negativo.
    /// </summary>
    Task<ProductDto> AdjustStockAsync(Guid id, AdjustStockRequest request, CancellationToken ct = default);
}
