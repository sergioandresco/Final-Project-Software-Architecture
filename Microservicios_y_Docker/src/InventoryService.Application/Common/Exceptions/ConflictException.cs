namespace InventoryService.Application.Common.Exceptions;

/// <summary>
/// Se lanza cuando una operación viola una regla de negocio de unicidad o estado.
/// La capa de presentación la traduce a un HTTP 409.
/// </summary>
public class ConflictException : Exception
{
    public ConflictException(string message) : base(message) { }
}
