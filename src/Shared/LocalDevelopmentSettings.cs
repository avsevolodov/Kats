using Microsoft.Extensions.Configuration;

namespace AgentPlatform;

internal static class LocalDevelopmentSettings
{
    public static void Load(ConfigurationManager configuration, bool development, string component, string[] args)
    {
        var profile = Environment.GetEnvironmentVariable("KATS_LOCAL_PROFILE");
        if (string.IsNullOrEmpty(profile)) return;
        if (!development || profile is not ("test" or "local"))
            throw new InvalidOperationException("KATS_LOCAL_PROFILE requires Development and test/local profile");
        // Find repo from build output, independent of Rider's working directory.
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root != null && !File.Exists(Path.Combine(root.FullName, "AgentPlatform.slnx"))) root = root.Parent;
        if (root == null) throw new InvalidOperationException("Local profile requires a source checkout");
        var path = Path.Combine(root.FullName, ".local", $"rider-{profile}-{component}.json");
        if (!File.Exists(path)) throw new InvalidOperationException("Generate Rider settings first: uv run scripts/test_env.py configure (test) or uv run scripts/dev.py rider (local)");
        configuration.AddJsonFile(path, optional: false, reloadOnChange: false);
        configuration.AddEnvironmentVariables();
        configuration.AddCommandLine(args);
    }
}
