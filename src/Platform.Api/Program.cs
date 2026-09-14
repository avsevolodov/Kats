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
using Microsoft.IdentityModel.Protocols.OpenIdConnect;

var builder = WebApplication.CreateBuilder(args);
if (builder.Environment.IsDevelopment()) builder.WebHost.UseStaticWebAssets();
builder.WebHost.ConfigureKestrel(k =>
{
    k.Limits.MaxRequestBodySize = 32 * 1024;
    k.ListenAnyIP(8080, l => l.Protocols = HttpProtocols.Http1);
    var browserCertificate = builder.Configuration["Browser:ServerCertificate"];
    // HTTP/1.1 avoids Extended CONNECT WebSocket path; stream still accepts CONNECT if enabled later.
    if (!string.IsNullOrEmpty(browserCertificate)) k.ListenAnyIP(8443, l =>
    {
        l.Protocols = HttpProtocols.Http1;
        l.UseHttps(browserCertificate, builder.Configuration["Browser:ServerCertificatePassword"]);
    });
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
var adminRole = builder.Configuration["Security:AdminRole"] ?? "admin";
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
        if (builder.Configuration.GetValue<bool>("Oidc:AllowLoopbackHttp"))
        {
            if (!builder.Environment.IsDevelopment() || !Uri.TryCreate(o.Authority, UriKind.Absolute, out var authority)
                || !authority.IsLoopback || authority.Scheme != "http")
                throw new InvalidOperationException("HTTP OIDC is restricted to Development loopback authorities");
            o.RequireHttpsMetadata = false;
        }
        o.ResponseType = OpenIdConnectResponseType.Code; o.UsePkce = true; o.SaveTokens = true; o.MapInboundClaims = false; o.GetClaimsFromUserInfoEndpoint = false;
        o.Scope.Clear(); o.Scope.Add("openid"); o.Scope.Add("profile");
        o.TokenValidationParameters.RoleClaimType = "roles";
        o.Events.OnTokenValidated = context =>
        {
            if (context.Principal?.Identity is not ClaimsIdentity identity) return Task.CompletedTask;
            foreach (var claim in context.Principal.FindAll("roles").ToList())
                if (!identity.HasClaim(ClaimTypes.Role, claim.Value)) identity.AddClaim(new Claim(ClaimTypes.Role, claim.Value));
            return Task.CompletedTask;
        };
    });
builder.Services.AddAuthorization(o => o.AddPolicy("Admin", p => p.RequireRole(adminRole)));
var app = builder.Build();
app.UseForwardedHeaders();
app.Use(async (context, next) =>
{
    try { await next(); }
    catch (PlatformException e) { if (!context.Response.HasStarted) { context.Response.StatusCode = e.Status; await context.Response.WriteAsJsonAsync(new { title = e.Code, status = e.Status, code = e.Code }); } }
    catch (AntiforgeryValidationException) { context.Response.StatusCode = 400; await context.Response.WriteAsJsonAsync(new { title = "CSRF validation failed", status = 400, code = "CSRF_INVALID" }); }
    catch (OperationCanceledException) when (context.RequestAborted.IsCancellationRequested) { }
});
// Do not combine the terminal /_framework branch of UseBlazorFrameworkFiles
// with endpoint-based static assets: it can swallow an already selected endpoint.
app.UseStaticFiles();
app.UseWebSockets();
app.UseAuthentication();
app.UseAuthorization();
// Fingerprinted URLs (including WASM Hot Reload initializers) are manifest endpoints,
// not physical filenames. Static file middleware alone cannot serve these aliases.
app.MapStaticAssets().AllowAnonymous();
app.MapGet("/health/live", () => Results.Ok(new { status = "alive" }));
app.MapGet("/health/ready", async (IDbContextFactory<PlatformDb> factory) => { await using var db = await factory.CreateDbContextAsync(); return await db.Database.CanConnectAsync() ? Results.Ok() : Results.StatusCode(503); });
app.MapGet("/login", () => Results.Challenge(new AuthenticationProperties { RedirectUri = "/" }, [OpenIdConnectDefaults.AuthenticationScheme]));
app.MapGet("/logout", async (HttpContext c) =>
{
    // SaveTokens stores id_token for Keycloak end_session id_token_hint.
    var redirect = new AuthenticationProperties { RedirectUri = "/" };
    await c.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme, redirect);
    await c.SignOutAsync(OpenIdConnectDefaults.AuthenticationScheme, redirect);
});
// Path match only (any method): HTTP/2 WebSocket is CONNECT; MapGet → 405.
app.Map("/api/v1/stream", async (HttpContext context, SqlStore store, IConfiguration config) =>
{
    if (context.User.Identity?.IsAuthenticated != true)
    {
        context.Response.StatusCode = StatusCodes.Status401Unauthorized;
        return;
    }
    await BrowserStream.Handle(context, store, config);
});
static string Owner(HttpContext c) => c.User.FindFirstValue("sub") ?? throw new PlatformException("UNAUTHENTICATED", 401);
static bool IsAdmin(HttpContext c, string role) => c.User.IsInRole(role);
var api = app.MapGroup("/api/v1").RequireAuthorization();
api.MapGet("/security/antiforgery", (HttpContext c, IAntiforgery a) => new { requestToken = a.GetAndStoreTokens(c).RequestToken, headerName = "X-CSRF-TOKEN" });
api.MapGet("/security/me", (HttpContext c) => Results.Ok(new SecurityMe(Owner(c), IsAdmin(c, adminRole))));
api.MapGet("/repositories", async (SqlStore s) => Results.Ok(new { items = await s.Repositories() }));
api.MapPost("/repositories", async (UpsertRepository body, HttpContext c, IAntiforgery a, SqlStore s) =>
{
    await a.ValidateRequestAsync(c);
    var created = await s.CreateRepository(body);
    return Results.Created($"/api/v1/repositories/{created.RepositoryId}", created);
});
api.MapPut("/repositories/{id:guid}", async (Guid id, UpsertRepository body, HttpContext c, IAntiforgery a, SqlStore s) =>
{
    await a.ValidateRequestAsync(c);
    return Results.Ok(await s.UpdateRepository(id, body));
});
api.MapDelete("/repositories/{id:guid}", async (Guid id, HttpContext c, IAntiforgery a, SqlStore s) =>
{
    await a.ValidateRequestAsync(c);
    await s.DisableRepository(id);
    return Results.NoContent();
});
api.MapGet("/runners", async (SqlStore s) => Results.Ok(new { items = await s.ListConnectedRunners() })).RequireAuthorization("Admin");
api.MapPost("/runs", async (StartRun r, HttpContext c, IAntiforgery a, SqlStore s) => { await a.ValidateRequestAsync(c); var result = await s.Start(Owner(c), r); return Results.Accepted(result.StatusUrl, result); });
api.MapGet("/runs", async (HttpContext c, SqlStore s) => Results.Ok(new { items = await s.List(Owner(c)), nextCursor = (string?)null }));
api.MapGet("/runs/{id:guid}", async (Guid id, HttpContext c, SqlStore s) => await s.Get(Owner(c), id));
api.MapPost("/runs/{id:guid}/cancel", async (Guid id, CancelRun r, HttpContext c, IAntiforgery a, SqlStore s) => { await a.ValidateRequestAsync(c); var result = await s.Cancel(Owner(c), id, r.CommandId); return Results.Accepted(result.StatusUrl, result); });
api.MapPost("/runs/{id:guid}/confirm", async (Guid id, ConfirmRun r, HttpContext c, IAntiforgery a, SqlStore s) => { await a.ValidateRequestAsync(c); var result = await s.Confirm(Owner(c), id, r); return Results.Accepted(result.StatusUrl, result); });
api.MapGet("/runs/{id:guid}/events", async (Guid id, HttpContext c, SqlStore s) => { var raw = c.Request.Query["afterSequence"].FirstOrDefault() ?? "0"; Rules.Require(long.TryParse(raw, out var n), "INVALID_CURSOR", 400); return await s.Events(Owner(c), id, n); });
api.MapGet("/runs/{id:guid}/artifacts/{artifact:guid}", async (Guid id, Guid artifact, HttpContext c, SqlStore s) => { var a = await s.Artifact(Owner(c), id, artifact); return Results.File(a.Content, "text/plain; charset=utf-8", a.Kind == "patch" ? "changes.patch" : "summary.txt"); });
// HTTP/1.1 WebSocket uses GET; HTTP/2 uses Extended CONNECT. MapGet → 405 on H2.
api.Map("/stream", BrowserStream.Handle);
app.MapGrpcService<RunnerService>();
app.MapFallbackToFile("index.html");
app.Run();
