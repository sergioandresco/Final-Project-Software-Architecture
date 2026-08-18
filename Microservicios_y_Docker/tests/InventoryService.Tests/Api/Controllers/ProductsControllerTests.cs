using InventoryService.Api.Controllers;
using InventoryService.Application.Common.Exceptions;
using InventoryService.Application.Products;
using InventoryService.Application.Products.Dtos;
using Microsoft.AspNetCore.Mvc;
using Moq;
using Xunit;

namespace InventoryService.Tests.Api.Controllers;

public class ProductsControllerTests
{
    private readonly Mock<IProductService> _serviceMock = new();
    private readonly ProductsController _controller;

    public ProductsControllerTests()
    {
        _controller = new ProductsController(_serviceMock.Object);
    }

    private static ProductDto SampleDto(Guid? id = null) => new(
        id ?? Guid.NewGuid(),
        "SKU-001",
        "Producto de prueba",
        "Descripción",
        100m,
        10,
        DateTime.UtcNow,
        DateTime.UtcNow);

    [Fact]
    public async Task GetAll_ReturnsOkWithProductsFromService()
    {
        var products = new List<ProductDto> { SampleDto(), SampleDto() };
        _serviceMock.Setup(s => s.GetAllAsync(It.IsAny<CancellationToken>())).ReturnsAsync(products);

        var result = await _controller.GetAll(CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Same(products, okResult.Value);
    }

    [Fact]
    public async Task GetById_WhenExists_ReturnsOkWithProduct()
    {
        var id = Guid.NewGuid();
        var dto = SampleDto(id);
        _serviceMock.Setup(s => s.GetByIdAsync(id, It.IsAny<CancellationToken>())).ReturnsAsync(dto);

        var result = await _controller.GetById(id, CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Same(dto, okResult.Value);
    }

    [Fact]
    public async Task GetById_WhenServiceThrowsNotFound_ExceptionPropagatesToMiddleware()
    {
        var id = Guid.NewGuid();
        _serviceMock.Setup(s => s.GetByIdAsync(id, It.IsAny<CancellationToken>()))
                    .ThrowsAsync(NotFoundException.For("producto", id));

        await Assert.ThrowsAsync<NotFoundException>(() => _controller.GetById(id, CancellationToken.None));
    }

    [Fact]
    public async Task Create_ReturnsCreatedAtAction_PointingToGetById()
    {
        var request = new CreateProductRequest { Sku = "SKU-001", Name = "Producto", Price = 10m, Quantity = 5 };
        var created = SampleDto();
        _serviceMock.Setup(s => s.CreateAsync(request, It.IsAny<CancellationToken>())).ReturnsAsync(created);

        var result = await _controller.Create(request, CancellationToken.None);

        var createdResult = Assert.IsType<CreatedAtActionResult>(result.Result);
        Assert.Equal(nameof(ProductsController.GetById), createdResult.ActionName);
        Assert.Equal(created.Id, (Guid)createdResult.RouteValues!["id"]!);
        Assert.Same(created, createdResult.Value);
    }

    [Fact]
    public async Task Create_WhenServiceThrowsConflict_ExceptionPropagatesToMiddleware()
    {
        var request = new CreateProductRequest { Sku = "SKU-DUP", Name = "Producto", Price = 10m, Quantity = 5 };
        _serviceMock.Setup(s => s.CreateAsync(request, It.IsAny<CancellationToken>()))
                    .ThrowsAsync(new ConflictException("Ya existe un producto con el SKU 'SKU-DUP'."));

        await Assert.ThrowsAsync<ConflictException>(() => _controller.Create(request, CancellationToken.None));
    }

    [Fact]
    public async Task Update_ReturnsOkWithUpdatedProduct()
    {
        var id = Guid.NewGuid();
        var request = new UpdateProductRequest { Name = "Actualizado", Price = 20m, Quantity = 15 };
        var updated = SampleDto(id);
        _serviceMock.Setup(s => s.UpdateAsync(id, request, It.IsAny<CancellationToken>())).ReturnsAsync(updated);

        var result = await _controller.Update(id, request, CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Same(updated, okResult.Value);
    }

    [Fact]
    public async Task Update_WhenServiceThrowsNotFound_ExceptionPropagatesToMiddleware()
    {
        var id = Guid.NewGuid();
        var request = new UpdateProductRequest { Name = "Actualizado", Price = 20m, Quantity = 15 };
        _serviceMock.Setup(s => s.UpdateAsync(id, request, It.IsAny<CancellationToken>()))
                    .ThrowsAsync(NotFoundException.For("producto", id));

        await Assert.ThrowsAsync<NotFoundException>(() => _controller.Update(id, request, CancellationToken.None));
    }

    [Fact]
    public async Task Delete_ReturnsNoContent_AndCallsService()
    {
        var id = Guid.NewGuid();
        _serviceMock.Setup(s => s.DeleteAsync(id, It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        var result = await _controller.Delete(id, CancellationToken.None);

        Assert.IsType<NoContentResult>(result);
        _serviceMock.Verify(s => s.DeleteAsync(id, It.IsAny<CancellationToken>()), Times.Once);
    }

    [Fact]
    public async Task Delete_WhenServiceThrowsNotFound_ExceptionPropagatesToMiddleware()
    {
        var id = Guid.NewGuid();
        _serviceMock.Setup(s => s.DeleteAsync(id, It.IsAny<CancellationToken>()))
                    .ThrowsAsync(NotFoundException.For("producto", id));

        await Assert.ThrowsAsync<NotFoundException>(() => _controller.Delete(id, CancellationToken.None));
    }

    [Fact]
    public async Task AdjustStock_ReturnsOkWithAdjustedProduct()
    {
        var id = Guid.NewGuid();
        var request = new AdjustStockRequest { Delta = -5 };
        var adjusted = SampleDto(id);
        _serviceMock.Setup(s => s.AdjustStockAsync(id, request, It.IsAny<CancellationToken>())).ReturnsAsync(adjusted);

        var result = await _controller.AdjustStock(id, request, CancellationToken.None);

        var okResult = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Same(adjusted, okResult.Value);
    }

    [Fact]
    public async Task AdjustStock_WhenServiceThrowsConflict_ExceptionPropagatesToMiddleware()
    {
        var id = Guid.NewGuid();
        var request = new AdjustStockRequest { Delta = -1000 };
        _serviceMock.Setup(s => s.AdjustStockAsync(id, request, It.IsAny<CancellationToken>()))
                    .ThrowsAsync(new ConflictException("Stock insuficiente"));

        await Assert.ThrowsAsync<ConflictException>(() => _controller.AdjustStock(id, request, CancellationToken.None));
    }
}
