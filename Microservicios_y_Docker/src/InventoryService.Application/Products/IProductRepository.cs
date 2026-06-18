using InventoryService.Domain.Entities;

namespace InventoryService.Application.Products;

/// <summary>
/// Puerto de persistencia que la capa Application necesita.
/// La implementación concreta vive en Infrastructure (regla de dependencia hacia adentro).
/// </summary>
public interface IProductRepository
{
    Task<IReadOnlyList<Product>> GetAllAsync(CancellationToken ct = default);

    Task<Product?> GetByIdAsync(Guid id, CancellationToken ct = default);

    Task<bool> SkuExistsAsync(string sku, CancellationToken ct = default);

    Task AddAsync(Product product, CancellationToken ct = default);

    void Update(Product product);

    void Remove(Product product);

    Task<int> SaveChangesAsync(CancellationToken ct = default);
}
