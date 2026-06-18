using InventoryService.Application.Common.Exceptions;
using Microsoft.AspNetCore.Mvc;

namespace InventoryService.Api.Middleware;

/// <summary>
/// Traduce las excepciones de la capa Application a respuestas HTTP (ProblemDetails).
/// Mantiene los controladores delgados y centraliza el manejo de errores.
/// </summary>
public class ExceptionHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ExceptionHandlingMiddleware> _logger;

    public ExceptionHandlingMiddleware(RequestDelegate next, ILogger<ExceptionHandlingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (Exception ex)
        {
            var (status, title) = ex switch
            {
                NotFoundException => (StatusCodes.Status404NotFound, "Recurso no encontrado"),
                ConflictException => (StatusCodes.Status409Conflict, "Conflicto"),
                _ => (StatusCodes.Status500InternalServerError, "Error interno del servidor")
            };

            if (status == StatusCodes.Status500InternalServerError)
                _logger.LogError(ex, "Error no controlado al procesar la solicitud.");

            var problem = new ProblemDetails
            {
                Status = status,
                Title = title,
                Detail = status == StatusCodes.Status500InternalServerError
                    ? "Ocurrió un error inesperado."
                    : ex.Message,
                Instance = context.Request.Path
            };

            context.Response.StatusCode = status;
            context.Response.ContentType = "application/problem+json";
            await context.Response.WriteAsJsonAsync(problem);
        }
    }
}
