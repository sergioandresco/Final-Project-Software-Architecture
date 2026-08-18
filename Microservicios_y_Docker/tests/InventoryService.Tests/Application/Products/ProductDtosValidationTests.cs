using System.ComponentModel.DataAnnotations;
using InventoryService.Application.Products.Dtos;
using Xunit;

namespace InventoryService.Tests.Application.Products;

public class ProductDtosValidationTests
{
    private static IList<ValidationResult> Validate(object instance)
    {
        var context = new ValidationContext(instance);
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(instance, context, results, validateAllProperties: true);
        return results;
    }

    [Theory]
    [InlineData("   ")]
    [InlineData("")]
    public void CreateProductRequest_WhenSkuIsWhitespace_FailsValidation(string sku)
    {
        var request = new CreateProductRequest { Sku = sku, Name = "Producto válido", Price = 1m, Quantity = 1 };

        var results = Validate(request);

        Assert.Contains(results, r => r.MemberNames.Contains(nameof(CreateProductRequest.Sku)));
    }

    [Fact]
    public void CreateProductRequest_WhenNameIsWhitespace_FailsValidation()
    {
        var request = new CreateProductRequest { Sku = "SKU-001", Name = "   ", Price = 1m, Quantity = 1 };

        var results = Validate(request);

        Assert.Contains(results, r => r.MemberNames.Contains(nameof(CreateProductRequest.Name)));
    }

    [Fact]
    public void CreateProductRequest_WithValidValues_PassesValidation()
    {
        var request = new CreateProductRequest { Sku = "SKU-001", Name = "Producto válido", Price = 1m, Quantity = 1 };

        var results = Validate(request);

        Assert.Empty(results);
    }

    [Fact]
    public void UpdateProductRequest_WhenNameIsWhitespace_FailsValidation()
    {
        var request = new UpdateProductRequest { Name = " ", Price = 1m, Quantity = 1 };

        var results = Validate(request);

        Assert.Contains(results, r => r.MemberNames.Contains(nameof(UpdateProductRequest.Name)));
    }

    [Fact]
    public void AdjustStockRequest_WhenDeltaIsZero_FailsValidation()
    {
        var request = new AdjustStockRequest { Delta = 0 };

        var results = Validate(request);

        Assert.Contains(results, r => r.MemberNames.Contains(nameof(AdjustStockRequest.Delta)));
    }

    [Theory]
    [InlineData(5)]
    [InlineData(-5)]
    public void AdjustStockRequest_WhenDeltaIsNonZero_PassesValidation(int delta)
    {
        var request = new AdjustStockRequest { Delta = delta };

        var results = Validate(request);

        Assert.Empty(results);
    }
}
