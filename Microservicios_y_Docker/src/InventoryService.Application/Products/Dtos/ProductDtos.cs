using System.ComponentModel.DataAnnotations;

namespace InventoryService.Application.Products.Dtos;

/// <summary>Datos que se devuelven al cliente.</summary>
public record ProductDto(
    Guid Id,
    string Sku,
    string Name,
    string? Description,
    decimal Price,
    int Quantity,
    DateTime CreatedAtUtc,
    DateTime UpdatedAtUtc);

/// <summary>Datos para crear un producto. Validación por DataAnnotations.</summary>
public class CreateProductRequest
{
    [Required, StringLength(50, MinimumLength = 1)]
    public string Sku { get; set; } = string.Empty;

    [Required, StringLength(200, MinimumLength = 1)]
    public string Name { get; set; } = string.Empty;

    [StringLength(1000)]
    public string? Description { get; set; }

    [Range(0, double.MaxValue, ErrorMessage = "El precio no puede ser negativo.")]
    public decimal Price { get; set; }

    [Range(0, int.MaxValue, ErrorMessage = "La cantidad no puede ser negativa.")]
    public int Quantity { get; set; }
}

/// <summary>Datos para actualizar un producto existente.</summary>
public class UpdateProductRequest
{
    [Required, StringLength(200, MinimumLength = 1)]
    public string Name { get; set; } = string.Empty;

    [StringLength(1000)]
    public string? Description { get; set; }

    [Range(0, double.MaxValue, ErrorMessage = "El precio no puede ser negativo.")]
    public decimal Price { get; set; }

    [Range(0, int.MaxValue, ErrorMessage = "La cantidad no puede ser negativa.")]
    public int Quantity { get; set; }
}
