using InventoryService.Application.Common.Exceptions;
using InventoryService.Application.Products;
using InventoryService.Domain.Entities;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace InventoryService.Infrastructure.Persistence.Repositories;

/// <summary>
/// Implementación del puerto <see cref="IProductRepository"/> con EF Core.
/// </summary>
public class ProductRepository : IProductRepository
{
    private readonly InventoryDbContext _db;

    public ProductRepository(InventoryDbContext db) => _db = db;

    public async Task<IReadOnlyList<Product>> GetAllAsync(CancellationToken ct = default)
        => await _db.Products
                    .AsNoTracking()
                    .OrderBy(p => p.Name)
                    .ToListAsync(ct);

    public async Task<Product?> GetByIdAsync(Guid id, CancellationToken ct = default)
        => await _db.Products.FirstOrDefaultAsync(p => p.Id == id, ct);

    public async Task<bool> SkuExistsAsync(string sku, CancellationToken ct = default)
        => await _db.Products.AnyAsync(p => p.Sku == sku, ct);

    public async Task AddAsync(Product product, CancellationToken ct = default)
        => await _db.Products.AddAsync(product, ct);

    public void Update(Product product) => _db.Products.Update(product);

    public void Remove(Product product) => _db.Products.Remove(product);

    public async Task<int> SaveChangesAsync(CancellationToken ct = default)
    {
        try
        {
            return await _db.SaveChangesAsync(ct);
        }
        catch (DbUpdateException ex) when (IsUniqueSkuViolation(ex))
        {
            throw new ConflictException("Ya existe un producto con el SKU proporcionado.");
        }
    }

    private static bool IsUniqueSkuViolation(DbUpdateException ex)
        => ex.InnerException is SqliteException { SqliteErrorCode: 19 };
}
