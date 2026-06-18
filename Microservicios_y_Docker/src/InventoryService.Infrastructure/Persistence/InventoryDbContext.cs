using InventoryService.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace InventoryService.Infrastructure.Persistence;

/// <summary>
/// Contexto de EF Core para el inventario.
/// Configura el mapeo de la entidad <see cref="Product"/> a la tabla correspondiente.
/// </summary>
public class InventoryDbContext : DbContext
{
    public InventoryDbContext(DbContextOptions<InventoryDbContext> options)
        : base(options)
    {
    }

    public DbSet<Product> Products => Set<Product>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<Product>(entity =>
        {
            entity.HasKey(p => p.Id);

            entity.Property(p => p.Sku)
                  .IsRequired()
                  .HasMaxLength(50);

            entity.HasIndex(p => p.Sku)
                  .IsUnique();

            entity.Property(p => p.Name)
                  .IsRequired()
                  .HasMaxLength(200);

            entity.Property(p => p.Description)
                  .HasMaxLength(1000);

            entity.Property(p => p.Price)
                  .HasColumnType("decimal(18,2)");
        });
    }
}
