# ============================================================
#  Dockerfile multi-stage para InventoryService
#  Etapa 1 (build): compila y publica con el SDK de .NET
#  Etapa 2 (final): imagen ligera solo con el runtime ASP.NET
# ============================================================

# ---------- Etapa de compilación ----------
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copiamos primero solo los .csproj para aprovechar la caché de capas:
# si no cambian, 'dotnet restore' no se vuelve a ejecutar.
COPY ["src/InventoryService.Domain/InventoryService.Domain.csproj", "src/InventoryService.Domain/"]
COPY ["src/InventoryService.Application/InventoryService.Application.csproj", "src/InventoryService.Application/"]
COPY ["src/InventoryService.Infrastructure/InventoryService.Infrastructure.csproj", "src/InventoryService.Infrastructure/"]
COPY ["src/InventoryService.Api/InventoryService.Api.csproj", "src/InventoryService.Api/"]
RUN dotnet restore "src/InventoryService.Api/InventoryService.Api.csproj"

# Ahora copiamos el resto del código y publicamos en Release.
COPY . .
RUN dotnet publish "src/InventoryService.Api/InventoryService.Api.csproj" \
    -c Release -o /app/publish /p:UseAppHost=false

# ---------- Etapa final (runtime) ----------
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS final
WORKDIR /app

# Usuario sin privilegios (buena práctica de seguridad para Kubernetes).
RUN adduser --disabled-password --gecos "" --uid 1001 appuser \
    && mkdir -p /data && chown appuser:appuser /data

COPY --from=build /app/publish .

# El proceso escucha en el 8080 (puerto no privilegiado).
ENV ASPNETCORE_URLS=http://+:8080
# Por defecto, la base SQLite se guarda en el volumen /data.
ENV ConnectionStrings__Default="Data Source=/data/inventory.db"

USER appuser
EXPOSE 8080

ENTRYPOINT ["dotnet", "InventoryService.Api.dll"]
