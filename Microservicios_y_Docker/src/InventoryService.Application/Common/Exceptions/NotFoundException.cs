namespace InventoryService.Application.Common.Exceptions;

/// <summary>
/// Se lanza cuando un recurso solicitado no existe.
/// La capa de presentación la traduce a un HTTP 404.
/// </summary>
public class NotFoundException : Exception
{
    public NotFoundException(string message) : base(message) { }

    public static NotFoundException For(string entity, object key)
        => new($"No se encontró {entity} con identificador '{key}'.");
}
