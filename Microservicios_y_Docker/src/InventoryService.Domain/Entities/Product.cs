namespace InventoryService.Domain.Entities;

/// <summary>
/// Representa un artículo del inventario.
/// Es la entidad central del dominio: no depende de EF Core ni de la API.
/// </summary>
public class Product
{
    public Guid Id { get; set; }

    /// <summary>Código único del artículo (Stock Keeping Unit).</summary>
    public string Sku { get; set; } = string.Empty;

    public string Name { get; set; } = string.Empty;

    public string? Description { get; set; }

    public decimal Price { get; set; }

    /// <summary>Cantidad disponible en inventario.</summary>
    public int Quantity { get; set; }

    public DateTime CreatedAtUtc { get; set; }

    public DateTime UpdatedAtUtc { get; set; }
}
