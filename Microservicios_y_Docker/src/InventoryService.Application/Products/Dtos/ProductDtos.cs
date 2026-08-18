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
public class CreateProductRequest : IValidatableObject
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

    // StringLength(MinimumLength = 1) por sí solo deja pasar cadenas de solo espacios
    // (ej. " "), que luego el servicio recorta a "" y persiste vacías.
    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (string.IsNullOrWhiteSpace(Sku))
            yield return new ValidationResult("El SKU no puede estar vacío ni contener solo espacios.", new[] { nameof(Sku) });

        if (string.IsNullOrWhiteSpace(Name))
            yield return new ValidationResult("El nombre no puede estar vacío ni contener solo espacios.", new[] { nameof(Name) });
    }
}

/// <summary>Datos para actualizar un producto existente.</summary>
public class UpdateProductRequest : IValidatableObject
{
    [Required, StringLength(200, MinimumLength = 1)]
    public string Name { get; set; } = string.Empty;

    [StringLength(1000)]
    public string? Description { get; set; }

    [Range(0, double.MaxValue, ErrorMessage = "El precio no puede ser negativo.")]
    public decimal Price { get; set; }

    [Range(0, int.MaxValue, ErrorMessage = "La cantidad no puede ser negativa.")]
    public int Quantity { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (string.IsNullOrWhiteSpace(Name))
            yield return new ValidationResult("El nombre no puede estar vacío ni contener solo espacios.", new[] { nameof(Name) });
    }
}

/// <summary>Datos para ajustar la cantidad en inventario de un producto (entradas/salidas de stock).</summary>
public class AdjustStockRequest : IValidatableObject
{
    /// <summary>Cantidad a sumar (positiva) o restar (negativa) del inventario actual.</summary>
    public int Delta { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (Delta == 0)
            yield return new ValidationResult("El ajuste de stock no puede ser cero.", new[] { nameof(Delta) });
    }
}
