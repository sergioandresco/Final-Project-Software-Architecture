using InventoryService.Application.Common.Exceptions;
using InventoryService.Application.Products;
using InventoryService.Application.Products.Dtos;
using InventoryService.Domain.Entities;
using Moq;
using Xunit;

namespace InventoryService.Tests.Application.Products;

public class ProductServiceTests
{
    private readonly Mock<IProductRepository> _repositoryMock = new();
    private readonly ProductService _service;

    public ProductServiceTests()
    {
        _service = new ProductService(_repositoryMock.Object);
    }

    private static Product SampleProduct(Guid? id = null, string sku = "SKU-001", int quantity = 10) => new()
    {
        Id = id ?? Guid.NewGuid(),
        Sku = sku,
        Name = "Producto de prueba",
        Description = "Descripción",
        Price = 100m,
        Quantity = quantity,
        CreatedAtUtc = DateTime.UtcNow.AddDays(-1),
        UpdatedAtUtc = DateTime.UtcNow.AddDays(-1)
    };

    [Fact]
    public async Task GetAllAsync_ReturnsAllProductsMappedToDto()
    {
        var products = new List<Product> { SampleProduct(), SampleProduct() };
        _repositoryMock.Setup(r => r.GetAllAsync(It.IsAny<CancellationToken>())).ReturnsAsync(products);

        var result = await _service.GetAllAsync();

        Assert.Equal(products.Count, result.Count);
        Assert.Equal(products[0].Sku, result[0].Sku);
    }

    [Fact]
    public async Task GetByIdAsync_WhenExists_ReturnsDto()
    {
        var product = SampleProduct();
        _repositoryMock.Setup(r => r.GetByIdAsync(product.Id, It.IsAny<CancellationToken>())).ReturnsAsync(product);

        var dto = await _service.GetByIdAsync(product.Id);

        Assert.Equal(product.Id, dto.Id);
        Assert.Equal(product.Sku, dto.Sku);
    }

    [Fact]
    public async Task GetByIdAsync_WhenNotFound_ThrowsNotFoundException()
    {
        var id = Guid.NewGuid();
        _repositoryMock.Setup(r => r.GetByIdAsync(id, It.IsAny<CancellationToken>())).ReturnsAsync((Product?)null);

        await Assert.ThrowsAsync<NotFoundException>(() => _service.GetByIdAsync(id));
    }

    [Fact]
    public async Task CreateAsync_WhenSkuIsNew_CreatesProductAndTrimsFields()
    {
        _repositoryMock.Setup(r => r.SkuExistsAsync("SKU-NEW", It.IsAny<CancellationToken>())).ReturnsAsync(false);

        var request = new CreateProductRequest
        {
            Sku = "  SKU-NEW  ",
            Name = "  Producto Nuevo  ",
            Description = "  Desc  ",
            Price = 50m,
            Quantity = 3
        };

        var dto = await _service.CreateAsync(request);

        Assert.Equal("SKU-NEW", dto.Sku);
        Assert.Equal("Producto Nuevo", dto.Name);
        Assert.Equal("Desc", dto.Description);
        _repositoryMock.Verify(
            r => r.AddAsync(It.Is<Product>(p => p.Sku == "SKU-NEW" && p.Name == "Producto Nuevo"), It.IsAny<CancellationToken>()),
            Times.Once);
        _repositoryMock.Verify(r => r.SaveChangesAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task CreateAsync_WhenSkuAlreadyExists_ThrowsConflictExceptionAndDoesNotPersist()
    {
        _repositoryMock.Setup(r => r.SkuExistsAsync("SKU-DUP", It.IsAny<CancellationToken>())).ReturnsAsync(true);

        var request = new CreateProductRequest { Sku = "SKU-DUP", Name = "Producto", Price = 10m, Quantity = 1 };

        await Assert.ThrowsAsync<ConflictException>(() => _service.CreateAsync(request));
        _repositoryMock.Verify(r => r.AddAsync(It.IsAny<Product>(), It.IsAny<CancellationToken>()), Times.Never);
        _repositoryMock.Verify(r => r.SaveChangesAsync(It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task UpdateAsync_WhenExists_UpdatesFieldsAndReturnsDto()
    {
        var product = SampleProduct();
        _repositoryMock.Setup(r => r.GetByIdAsync(product.Id, It.IsAny<CancellationToken>())).ReturnsAsync(product);

        var request = new UpdateProductRequest { Name = "Nombre Actualizado", Description = "Nueva desc", Price = 200m, Quantity = 25 };

        var dto = await _service.UpdateAsync(product.Id, request);

        Assert.Equal("Nombre Actualizado", dto.Name);
        Assert.Equal(200m, dto.Price);
        Assert.Equal(25, dto.Quantity);
        _repositoryMock.Verify(r => r.Update(product), Times.Once);
        _repositoryMock.Verify(r => r.SaveChangesAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task UpdateAsync_WhenNotFound_ThrowsNotFoundException()
    {
        var id = Guid.NewGuid();
        _repositoryMock.Setup(r => r.GetByIdAsync(id, It.IsAny<CancellationToken>())).ReturnsAsync((Product?)null);

        var request = new UpdateProductRequest { Name = "X", Price = 1m, Quantity = 1 };

        await Assert.ThrowsAsync<NotFoundException>(() => _service.UpdateAsync(id, request));
    }

    [Fact]
    public async Task DeleteAsync_WhenExists_RemovesProduct()
    {
        var product = SampleProduct();
        _repositoryMock.Setup(r => r.GetByIdAsync(product.Id, It.IsAny<CancellationToken>())).ReturnsAsync(product);

        await _service.DeleteAsync(product.Id);

        _repositoryMock.Verify(r => r.Remove(product), Times.Once);
        _repositoryMock.Verify(r => r.SaveChangesAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task DeleteAsync_WhenNotFound_ThrowsNotFoundException()
    {
        var id = Guid.NewGuid();
        _repositoryMock.Setup(r => r.GetByIdAsync(id, It.IsAny<CancellationToken>())).ReturnsAsync((Product?)null);

        await Assert.ThrowsAsync<NotFoundException>(() => _service.DeleteAsync(id));
    }

    [Theory]
    [InlineData(5, 15)]
    [InlineData(-4, 6)]
    public async Task AdjustStockAsync_WhenResultIsNonNegative_UpdatesQuantity(int delta, int expectedQuantity)
    {
        var product = SampleProduct(quantity: 10);
        _repositoryMock.Setup(r => r.GetByIdAsync(product.Id, It.IsAny<CancellationToken>())).ReturnsAsync(product);

        var dto = await _service.AdjustStockAsync(product.Id, new AdjustStockRequest { Delta = delta });

        Assert.Equal(expectedQuantity, dto.Quantity);
        _repositoryMock.Verify(r => r.SaveChangesAsync(It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task AdjustStockAsync_WhenResultWouldBeNegative_ThrowsConflictExceptionAndDoesNotSave()
    {
        var product = SampleProduct(quantity: 3);
        _repositoryMock.Setup(r => r.GetByIdAsync(product.Id, It.IsAny<CancellationToken>())).ReturnsAsync(product);

        await Assert.ThrowsAsync<ConflictException>(
            () => _service.AdjustStockAsync(product.Id, new AdjustStockRequest { Delta = -10 }));

        Assert.Equal(3, product.Quantity);
        _repositoryMock.Verify(r => r.SaveChangesAsync(It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task AdjustStockAsync_WhenNotFound_ThrowsNotFoundException()
    {
        var id = Guid.NewGuid();
        _repositoryMock.Setup(r => r.GetByIdAsync(id, It.IsAny<CancellationToken>())).ReturnsAsync((Product?)null);

        await Assert.ThrowsAsync<NotFoundException>(
            () => _service.AdjustStockAsync(id, new AdjustStockRequest { Delta = 1 }));
    }
}
