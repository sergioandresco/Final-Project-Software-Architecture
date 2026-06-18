using InventoryService.Application.Common.Exceptions;
using InventoryService.Application.Products.Dtos;
using InventoryService.Domain.Entities;

namespace InventoryService.Application.Products;

/// <summary>
/// Implementación de los casos de uso del inventario.
/// Contiene la lógica de aplicación: validación de reglas, orquestación y mapeo a DTOs.
/// Depende solo del puerto IProductRepository, nunca de EF Core.
/// </summary>
public class ProductService : IProductService
{
    private readonly IProductRepository _repository;

    public ProductService(IProductRepository repository) => _repository = repository;

    public async Task<IReadOnlyList<ProductDto>> GetAllAsync(CancellationToken ct = default)
    {
        var products = await _repository.GetAllAsync(ct);
        return products.Select(ToDto).ToList();
    }

    public async Task<ProductDto> GetByIdAsync(Guid id, CancellationToken ct = default)
    {
        var product = await _repository.GetByIdAsync(id, ct)
                      ?? throw NotFoundException.For("producto", id);
        return ToDto(product);
    }

    public async Task<ProductDto> CreateAsync(CreateProductRequest request, CancellationToken ct = default)
    {
        var sku = request.Sku.Trim();
        if (await _repository.SkuExistsAsync(sku, ct))
            throw new ConflictException($"Ya existe un producto con el SKU '{sku}'.");

        var now = DateTime.UtcNow;
        var product = new Product
        {
            Id = Guid.NewGuid(),
            Sku = sku,
            Name = request.Name.Trim(),
            Description = request.Description?.Trim(),
            Price = request.Price,
            Quantity = request.Quantity,
            CreatedAtUtc = now,
            UpdatedAtUtc = now
        };

        await _repository.AddAsync(product, ct);
        await _repository.SaveChangesAsync(ct);

        return ToDto(product);
    }

    public async Task<ProductDto> UpdateAsync(Guid id, UpdateProductRequest request, CancellationToken ct = default)
    {
        var product = await _repository.GetByIdAsync(id, ct)
                      ?? throw NotFoundException.For("producto", id);

        product.Name = request.Name.Trim();
        product.Description = request.Description?.Trim();
        product.Price = request.Price;
        product.Quantity = request.Quantity;
        product.UpdatedAtUtc = DateTime.UtcNow;

        _repository.Update(product);
        await _repository.SaveChangesAsync(ct);

        return ToDto(product);
    }

    public async Task DeleteAsync(Guid id, CancellationToken ct = default)
    {
        var product = await _repository.GetByIdAsync(id, ct)
                      ?? throw NotFoundException.For("producto", id);

        _repository.Remove(product);
        await _repository.SaveChangesAsync(ct);
    }

    private static ProductDto ToDto(Product p) => new(
        p.Id, p.Sku, p.Name, p.Description, p.Price, p.Quantity, p.CreatedAtUtc, p.UpdatedAtUtc);
}
