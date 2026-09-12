using System.Security.Claims;
using System.Security.Cryptography.X509Certificates;
using AgentPlatform;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.AspNetCore.Server.Kestrel.Https;
using Microsoft.AspNetCore.HttpOverrides;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(k =>
{
    k.Limits.MaxRequestBodySize = 32 * 1024;
    k.ListenAnyIP(8080, l => l.Protocols = HttpProtocols.Http1);
    var path = builder.Configuration["Runner:ServerCertificate"];
    if (!string.IsNullOrEmpty(path)) k.ListenAnyIP(8081, l =>
    {
        l.Protocols = HttpProtocols.Http2;
        l.UseHttps(o =>
        {
            o.ServerCertificate = X509CertificateLoader.LoadPkcs12FromFile(path, builder.Configuration["Runner:ServerCertificatePassword"]);
            o.ClientCertificateMode = ClientCertificateMode.RequireCertificate;
            var allowed = builder.Configuration.GetSection("Runner:AllowedThumbprints").Get<string[]>() ?? [];
            o.ClientCertificateValidation = (cert, chain, errors) => cert.NotBefore.ToUniversalTime() <= DateTime.UtcNow && cert.NotAfter.ToUniversalTime() > DateTime.UtcNow && allowed.Contains(cert.Thumbprint, StringComparer.OrdinalIgnoreCase);
        });
    });
    else if (!builder.Environment.IsDevelopment()) throw new InvalidOperationException("Runner server TLS certificate required");
});
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedProto | ForwardedHeaders.XForwardedFor;
    foreach (var ip in builder.Configuration.GetSection("Security:TrustedProxies").Get<string[]>() ?? []) o.KnownProxies.Add(System.Net.IPAddress.Parse(ip));
});
builder.Services.AddDbContextFactory<PlatformDb>(o => o.UseSqlServer(builder.Configuration.GetConnectionString("Platform") ?? throw new InvalidOperationException("ConnectionStrings:Platform required")));
builder.Services.AddSingleton<SqlStore>();
builder.Services.AddGrpc(o => { o.MaxReceiveMessageSize = 6 * 1024 * 1024; o.MaxSendMessageSize = 6 * 1024 * 1024; });
builder.Services.AddAntiforgery(o => o.HeaderName = "X-CSRF-TOKEN");
var protection = builder.Services.AddDataProtection().SetApplicationName("AgentPlatformMvp").PersistKeysToDbContext<PlatformDb>();
var keyPath = builder.Configuration["Security:DataProtectionCertificate"];
if (!string.IsNullOrEmpty(keyPath)) protection.ProtectKeysWithCertificate(X509CertificateLoader.LoadPkcs12FromFile(keyPath, builder.Configuration["Security:DataProtectionPassword"]));
else if (!builder.Environment.IsDevelopment()) throw new InvalidOperationException("Data Protection encryption certificate required");
builder.Services.AddAuthentication(o => { o.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme; o.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme; })
    .AddCookie(o =>
    {
        o.Cookie.Name = "__Host-AgentPlatform"; o.Cookie.SecurePolicy = CookieSecurePolicy.Always; o.Cookie.HttpOnly = true; o.Cookie.SameSite = SameSiteMode.Lax;
        o.ExpireTimeSpan = TimeSpan.FromHours(1); o.SlidingExpiration = false;
        o.Events.OnRedirectToLogin = c => { c.Response.StatusCode = 401; return Task.CompletedTask; };
    })
    .AddOpenIdConnect(o =>
    {
        o.Authority = builder.Configuration["Oidc:Authority"]; o.ClientId = builder.Configuration["Oidc:ClientId"]; o.ClientSecret = builder.Configuration["Oidc:ClientSecret"];
        o.ResponseType = "code"; o.UsePkce = true; o.SaveTokens = false; o.MapInboundClaims = false; o.GetClaimsFromUserInfoEndpoint = false;
    });
builder.Services.AddAuthorization();
var app = builder.Build();
app.UseForwardedHeaders();
app.Use(async (context, next) =>
{
    try { await next(); }
    catch (PlatformException e) { if (!context.Response.HasStarted) { context.Response.StatusCode = e.Status; await context.Response.WriteAsJsonAsync(new { title = e.Code, status = e.Status, code = e.Code }); } }
    catch (AntiforgeryValidationException) { context.Response.StatusCode = 400; await context.Response.WriteAsJsonAsync(new { title = "CSRF validation failed", status = 400, code = "CSRF_INVALID" }); }
    catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested) { }
});
app.UseBlazorFrameworkFiles(); app.UseStaticFiles(); app.UseWebSockets(); app.UseAuthentication(); app.UseAuthorization();
app.MapGet("/health/live", () => Results.Ok(new { status = "alive" }));
app.MapGet("/health/ready", async (IDbContextFactory<PlatformDb> factory) => { await using var db = await factory.CreateDbContextAsync(); return await db.Database.CanConnectAsync() ? Results.Ok() : Results.StatusCode(503); });
app.MapGet("/login", () => Results.Challenge(new AuthenticationProperties { RedirectUri = "/" }, [OpenIdConnectDefaults.AuthenticationScheme]));
static string Owner(HttpContext c) => c.User.FindFirstValue("sub") ?? throw new PlatformException("UNAUTHENTICATED", 401);
var api = app.MapGroup("/api/v1").RequireAuthorization();
api.MapGet("/security/antiforgery", (HttpContext c, IAntiforgery a) => new { requestToken = a.GetAndStoreTokens(c).RequestToken, headerName = "X-CSRF-TOKEN" });
api.MapGet("/repositories", async (SqlStore s) => Results.Ok(new { items = await s.Repositories() }));
api.MapPost("/runs", async (StartRun r, HttpContext c, IAntiforgery a, SqlStore s) => { await a.ValidateRequestAsync(c); var result = await s.Start(Owner(c), r); return Results.Accepted(result.StatusUrl, result); });
api.MapGet("/runs", async (HttpContext c, SqlStore s) => Results.Ok(new { items = await s.List(Owner(c)), nextCursor = (string?)null }));
api.MapGet("/runs/{id:guid}", async (Guid id, HttpContext c, SqlStore s) => await s.Get(Owner(c), id));
api.MapPost("/runs/{id:guid}/cancel", async (Guid id, CancelRun r, HttpContext c, IAntiforgery a, SqlStore s) => { await a.ValidateRequestAsync(c); var result = await s.Cancel(Owner(c), id, r.CommandId); return Results.Accepted(result.StatusUrl, result); });
api.MapGet("/runs/{id:guid}/events", async (Guid id, HttpContext c, SqlStore s) => { var raw = c.Request.Query["afterSequence"].FirstOrDefault() ?? "0"; Rules.Require(long.TryParse(raw, out var n), "INVALID_CURSOR", 400); return await s.Events(Owner(c), id, n); });
api.MapGet("/runs/{id:guid}/artifacts/{artifact:guid}", async (Guid id, Guid artifact, HttpContext c, SqlStore s) => { var a = await s.Artifact(Owner(c), id, artifact); return Results.File(a.Content, "text/plain; charset=utf-8", a.Kind == "patch" ? "changes.patch" : "summary.txt"); });
api.MapGet("/stream", BrowserStream.Handle);
app.MapGrpcService<RunnerService>();
app.MapFallbackToFile("index.html");
app.Run();
