using System.Diagnostics;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;

namespace ClaudeZh.Launcher;

internal static class Program
{
    private const string PayloadResource = "ClaudeZh.Payload.zip";
    private const string CacheOverride = "CLAUDE_ZH_LAUNCHER_CACHE";
    private const string ManifestName = "manifest.sha256";
    private const string RuntimePath = "runtime/node.exe";
    private const string EntryPath = "app/bin/claude-zh.cjs";
    private const string PtySmokePath = "app/launcher/pty-smoke.cjs";

    private sealed record ManifestEntry(string Hash, long Length, string RelativePath);

    public static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);
        Console.Title = "claude-zh-bilingual";

        try
        {
            string payloadHash = ComputePayloadHash();
            string version = GetVersion();
            if (args.Length == 1 && args[0] == "--launcher-version")
            {
                Console.WriteLine($"claude-zh launcher {version}");
                Console.WriteLine($"payload-sha256 {payloadHash}");
                return 0;
            }

            string cacheRoot = GetCacheRoot(version, payloadHash);
            EnsurePayload(cacheRoot, payloadHash);
            if (args.Length == 1 && args[0] == "--launcher-self-test")
            {
                return RunNodeScript(cacheRoot, PtySmokePath, []);
            }
            string[] forwarded = args.Length == 0 ? PromptForAction() : args;
            if (forwarded.Length == 0)
            {
                return 0;
            }

            int exitCode = RunNode(cacheRoot, forwarded);
            if (args.Length == 0 && !Console.IsInputRedirected)
            {
                Console.WriteLine();
                Console.Write("操作完成。按 Enter 关闭窗口...");
                Console.ReadLine();
            }
            return exitCode;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"[LAUNCHER_FAILED] {error.Message}");
            if (args.Length == 0 && !Console.IsInputRedirected)
            {
                Console.Error.Write("按 Enter 关闭窗口...");
                Console.ReadLine();
            }
            return 1;
        }
    }

    private static string[] PromptForAction()
    {
        Console.WriteLine("claude-zh-bilingual · Windows 启动器");
        Console.WriteLine("安装或还原前，请先正常退出 Claude。");
        Console.WriteLine();
        Console.WriteLine("  1. Desktop 中英对照模式（推荐）");
        Console.WriteLine("  2. Desktop 纯中文模式");
        Console.WriteLine("  3. Claude Code A 层中英对照模式");
        Console.WriteLine("  4. Claude Code A 层纯中文模式");
        Console.WriteLine("  5. 查看 Desktop 状态");
        Console.WriteLine("  6. 查看 Claude Code 状态");
        Console.WriteLine("  7. 还原 Desktop");
        Console.WriteLine("  8. 还原 Claude Code A 层");
        Console.WriteLine("  9. 运行实验性 Claude Code B 层");
        Console.WriteLine("  0. 退出");
        Console.WriteLine();
        Console.Write("请选择 [0-9]: ");

        return Console.ReadLine()?.Trim() switch
        {
            "1" => ["install", "desktop", "--mode=bilingual"],
            "2" => ["install", "desktop", "--mode=zh"],
            "3" => ["install", "code", "--layer=a", "--mode=bilingual"],
            "4" => ["install", "code", "--layer=a", "--mode=zh"],
            "5" => ["status", "desktop"],
            "6" => ["status", "code"],
            "7" => ["restore", "desktop"],
            "8" => ["restore", "code"],
            "9" => PromptForLayerBBinary(),
            _ => [],
        };
    }

    private static string[] PromptForLayerBBinary()
    {
        Console.Write("请输入 Claude Code 2.1.220 claude.exe 的完整路径: ");
        string binaryPath = (Console.ReadLine() ?? string.Empty).Trim().Trim('"');
        if (binaryPath.Length == 0)
        {
            return [];
        }
        if (!File.Exists(binaryPath))
        {
            throw new FileNotFoundException("没有找到指定的 Claude Code 程序。", binaryPath);
        }
        return ["run", "code", "--layer=b", $"--binary={Path.GetFullPath(binaryPath)}"];
    }

    private static int RunNode(string cacheRoot, IReadOnlyList<string> arguments)
    {
        return RunNodeScript(cacheRoot, EntryPath, arguments);
    }

    private static int RunNodeScript(
        string cacheRoot,
        string relativeEntry,
        IReadOnlyList<string> arguments
    )
    {
        string nodePath = ResolveInside(cacheRoot, RuntimePath);
        string entryPath = ResolveInside(cacheRoot, relativeEntry);
        ProcessStartInfo startInfo = new()
        {
            FileName = nodePath,
            UseShellExecute = false,
            WorkingDirectory = Environment.CurrentDirectory,
        };
        startInfo.ArgumentList.Add(entryPath);
        foreach (string argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }
        startInfo.Environment["CLAUDE_ZH_PORTABLE"] = "1";

        using Process process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("无法启动内置 Node 运行时。");
        process.WaitForExit();
        return process.ExitCode;
    }

    private static string GetVersion()
    {
        Version? version = Assembly.GetExecutingAssembly().GetName().Version;
        return version is null
            ? "0.0.0"
            : $"{version.Major}.{version.Minor}.{version.Build}";
    }

    private static Stream OpenPayload()
    {
        return Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadResource)
            ?? throw new InvalidDataException($"缺少内置资源 {PayloadResource}。");
    }

    private static string ComputePayloadHash()
    {
        using Stream payload = OpenPayload();
        return Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
    }

    private static string GetCacheRoot(string version, string payloadHash)
    {
        string? overridden = Environment.GetEnvironmentVariable(CacheOverride);
        string baseRoot = string.IsNullOrWhiteSpace(overridden)
            ? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
            : Path.GetFullPath(overridden);
        if (string.IsNullOrWhiteSpace(baseRoot))
        {
            throw new InvalidOperationException("无法确定本地应用数据目录。");
        }
        return Path.Combine(
            baseRoot,
            "claude-zh",
            "portable",
            $"v{version}-{payloadHash[..12]}"
        );
    }

    private static void EnsurePayload(string cacheRoot, string payloadHash)
    {
        string mutexName = $"Local\\ClaudeZhLauncher-{payloadHash[..24]}";
        using Mutex mutex = new(initiallyOwned: false, mutexName);
        if (!mutex.WaitOne(TimeSpan.FromSeconds(60)))
        {
            throw new TimeoutException("等待另一个启动器完成初始化时超时。");
        }

        try
        {
            if (ValidatePayload(cacheRoot))
            {
                return;
            }

            string parent = Directory.GetParent(cacheRoot)?.FullName
                ?? throw new InvalidOperationException("缓存目录没有父目录。");
            Directory.CreateDirectory(parent);
            if (Directory.Exists(cacheRoot))
            {
                Directory.Delete(cacheRoot, recursive: true);
            }

            string staging = Path.Combine(
                parent,
                $".staging-{Environment.ProcessId}-{Guid.NewGuid():N}"
            );
            try
            {
                Directory.CreateDirectory(staging);
                ExtractPayload(staging);
                if (!ValidatePayload(staging))
                {
                    throw new InvalidDataException("内置运行文件未通过 SHA-256 校验。");
                }
                Directory.Move(staging, cacheRoot);
            }
            finally
            {
                if (Directory.Exists(staging))
                {
                    Directory.Delete(staging, recursive: true);
                }
            }
        }
        finally
        {
            mutex.ReleaseMutex();
        }
    }

    private static void ExtractPayload(string destination)
    {
        using Stream payload = OpenPayload();
        using ZipArchive archive = new(payload, ZipArchiveMode.Read, leaveOpen: false);
        foreach (ZipArchiveEntry entry in archive.Entries)
        {
            string outputPath = ResolveInside(destination, entry.FullName);
            if (entry.FullName.EndsWith("/", StringComparison.Ordinal))
            {
                Directory.CreateDirectory(outputPath);
                continue;
            }

            string? parent = Path.GetDirectoryName(outputPath);
            if (parent is not null)
            {
                Directory.CreateDirectory(parent);
            }
            using Stream source = entry.Open();
            using FileStream target = new(outputPath, FileMode.CreateNew, FileAccess.Write);
            source.CopyTo(target);
        }
    }

    private static bool ValidatePayload(string root)
    {
        try
        {
            string manifestPath = ResolveInside(root, ManifestName);
            if (!File.Exists(manifestPath))
            {
                return false;
            }

            Dictionary<string, ManifestEntry> expected = new(
                StringComparer.OrdinalIgnoreCase
            );
            foreach (string line in File.ReadLines(manifestPath, Encoding.UTF8))
            {
                string[] parts = line.Split('\t', 3);
                if (
                    parts.Length != 3
                    || parts[0].Length != 64
                    || !long.TryParse(parts[1], out long length)
                )
                {
                    return false;
                }
                string relative = NormalizeRelative(parts[2]);
                expected.Add(
                    relative,
                    new ManifestEntry(parts[0].ToLowerInvariant(), length, relative)
                );
            }

            foreach (ManifestEntry entry in expected.Values)
            {
                string filename = ResolveInside(root, entry.RelativePath);
                FileInfo info = new(filename);
                if (!info.Exists || info.Length != entry.Length)
                {
                    return false;
                }
                using FileStream stream = info.OpenRead();
                string actual = Convert.ToHexString(SHA256.HashData(stream))
                    .ToLowerInvariant();
                if (!CryptographicOperations.FixedTimeEquals(
                    Encoding.ASCII.GetBytes(actual),
                    Encoding.ASCII.GetBytes(entry.Hash)
                ))
                {
                    return false;
                }
            }

            HashSet<string> actualFiles = Directory
                .EnumerateFiles(root, "*", SearchOption.AllDirectories)
                .Select(filename => NormalizeRelative(Path.GetRelativePath(root, filename)))
                .Where(relative => !relative.Equals(
                    ManifestName,
                    StringComparison.OrdinalIgnoreCase
                ))
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            return actualFiles.SetEquals(expected.Keys)
                && expected.ContainsKey(NormalizeRelative(RuntimePath))
                && expected.ContainsKey(NormalizeRelative(EntryPath))
                && expected.ContainsKey(NormalizeRelative(PtySmokePath));
        }
        catch (
            Exception error
        ) when (
            error is IOException
            or UnauthorizedAccessException
            or InvalidDataException
            or ArgumentException
        )
        {
            return false;
        }
    }

    private static string ResolveInside(string root, string relativePath)
    {
        string normalized = NormalizeRelative(relativePath);
        if (Path.IsPathRooted(normalized))
        {
            throw new InvalidDataException($"内置文件路径必须是相对路径：{relativePath}");
        }

        string rootPath = Path.GetFullPath(root);
        string fullPath = Path.GetFullPath(Path.Combine(rootPath, normalized));
        string prefix = rootPath.TrimEnd(
            Path.DirectorySeparatorChar,
            Path.AltDirectorySeparatorChar
        ) + Path.DirectorySeparatorChar;
        if (!fullPath.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"内置文件路径越界：{relativePath}");
        }
        return fullPath;
    }

    private static string NormalizeRelative(string value)
    {
        return value
            .Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar)
            .TrimStart(Path.DirectorySeparatorChar);
    }
}
