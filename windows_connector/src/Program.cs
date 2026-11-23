using System;
using System.Collections.Generic;

namespace Vortexen.PlanSwiftConnector
{
    public static class Program
    {
        private static volatile bool _cancelled;

        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                PrintUsage();
                return 0;
            }

            Console.CancelKeyPress += (sender, e) =>
            {
                e.Cancel = true;
                _cancelled = true;
                Console.Error.WriteLine("Cancellation requested; stopping COM traversal cleanly...");
            };

            string command = args[0].ToLowerInvariant();
            string outPath = GetArgValue(args, "--out");
            string progId = GetArgValue(args, "--progid");
            string uploadUrl = GetArgValue(args, "--upload-url");
            string projectId = GetArgValue(args, "--project-id");
            string token = GetArgValue(args, "--token");
            string connectorToken = GetArgValue(args, "--connector-token");
            string email = GetArgValue(args, "--email");
            string password = GetArgValue(args, "--password");
            string mode = (GetArgValue(args, "--mode") ?? "fast").ToLowerInvariant();
            string expectedGuid = GetArgValue(args, "--expected-guid");
            string maxSecondsRaw = GetArgValue(args, "--max-seconds");
            string connectTimeoutRaw = GetArgValue(args, "--connect-timeout");
            bool allowInsecureLocal = HasFlag(args, "--allow-insecure-local");
            bool includePoints = HasFlag(args, "--include-points");
            bool allowRoot = HasFlag(args, "--allow-root");
            bool skipPageDimensions = HasFlag(args, "--skip-page-dimensions");
            bool pagesOnly = HasFlag(args, "--pages-only");

            int maxSeconds = 300;
            if (!string.IsNullOrWhiteSpace(maxSecondsRaw))
            {
                if (!int.TryParse(maxSecondsRaw, out maxSeconds) || maxSeconds < 0)
                {
                    Console.Error.WriteLine("Invalid --max-seconds value: " + maxSecondsRaw);
                    return 1;
                }
            }

            int connectTimeoutSeconds = 20;
            if (!string.IsNullOrWhiteSpace(connectTimeoutRaw))
            {
                if (!int.TryParse(connectTimeoutRaw, out connectTimeoutSeconds) || connectTimeoutSeconds < 0)
                {
                    Console.Error.WriteLine("Invalid --connect-timeout value: " + connectTimeoutRaw);
                    return 1;
                }
            }

            try
            {
                if (command == "--health")
                {
                    var env = PlanSwiftVersionDetector.Detect(progId);
                    var health = new Dictionary<string, object>
                    {
                        { "status", "ok" },
                        { "agent", "VortexenPlanSwiftConnector" },
                        { "version", "1.2.4" },
                        { "is_64_bit_process", env.Is64BitProcess },
                        { "is_user_interactive", env.IsUserInteractive },
                        { "com_ready", env.ComReady },
                        { "registered_progids", env.RegisteredProgIds },
                        { "notes", env.Notes }
                    };
                    Console.WriteLine(CanonicalPayloadBuilder.SerializeJson(health));
                    return 0;
                }

                if (command == "--detect")
                {
                    var env = PlanSwiftVersionDetector.Detect(progId);
                    Console.WriteLine(CanonicalPayloadBuilder.SerializeJson(env));
                    return 0;
                }

                if (command == "--self-test")
                {
                    return RunSelfTest();
                }

                if (command == "--extract-com")
                {
                    if (mode != "fast" && mode != "full")
                    {
                        throw new ArgumentException("Invalid --mode '" + mode + "'. Supported modes: fast, full.");
                    }

                    var env = PlanSwiftVersionDetector.Detect(progId);
                    string targetProgId = !string.IsNullOrWhiteSpace(progId) ? progId : env.RecommendedProgId;
                    if (string.IsNullOrWhiteSpace(targetProgId) || !env.ComReady)
                    {
                        Console.Error.WriteLine(CanonicalPayloadBuilder.SerializeJson(new
                        {
                            error = "PLANSWIFT_COM_UNAVAILABLE",
                            message = env.Notes,
                            detected = env
                        }));
                        return 2;
                    }

                    // Validate upload target and authenticate BEFORE COM extraction so auth/network errors fail in <1s
                    if (!string.IsNullOrWhiteSpace(uploadUrl))
                    {
                        if (string.IsNullOrWhiteSpace(projectId))
                        {
                            throw new ArgumentException("--project-id <uuid> is required when --upload-url is provided.");
                        }
                        if (string.IsNullOrWhiteSpace(token) && !string.IsNullOrWhiteSpace(email) && !string.IsNullOrWhiteSpace(password))
                        {
                            Console.WriteLine("Authenticating with Vortexen backend before COM extraction...");
                            Console.Out.Flush();
                            string loginUrl = DeriveLoginUrl(uploadUrl);
                            token = SecureBackendUploader.LoginForAccessToken(loginUrl, email, password, requireTls: !allowInsecureLocal);
                        }
                    }

                    bool jsonOnlyStdout = string.IsNullOrWhiteSpace(outPath) && string.IsNullOrWhiteSpace(uploadUrl);
                    var options = new ComExtractionOptions
                    {
                        FastMode = mode == "fast",
                        PagesOnly = pagesOnly,
                        IncludePoints = includePoints,
                        AllowRootFallback = allowRoot,
                        ExpectedJobGuid = expectedGuid,
                        ConnectTimeoutSeconds = connectTimeoutSeconds,
                        SkipPageDimensions = skipPageDimensions,
                        MaxSeconds = maxSeconds,
                        IsCancelled = () => _cancelled,
                        ProgressWriter = jsonOnlyStdout ? Console.Error : Console.Out
                    };

                    var extractor = new ReadOnlyComExtractor(targetProgId, options);
                    var snapshot = extractor.ExtractCurrentJob();
                    string snapshotJson = CanonicalPayloadBuilder.SerializeJson(snapshot);

                    if (!string.IsNullOrWhiteSpace(outPath))
                    {
                        CanonicalPayloadBuilder.WriteJsonFile(outPath, snapshotJson);
                        Console.WriteLine(string.Format("Wrote COM snapshot ({0} objects) to {1}", snapshot.objects.Count, outPath));
                    }
                    else if (string.IsNullOrWhiteSpace(uploadUrl))
                    {
                        Console.WriteLine(snapshotJson);
                    }

                    if (!string.IsNullOrWhiteSpace(uploadUrl))
                    {
                        Console.WriteLine("Uploading COM snapshot to " + uploadUrl + " ...");
                        Console.Out.Flush();
                        string ingestBody = CanonicalPayloadBuilder.SerializeJson(new Dictionary<string, object>
                        {
                            { "project_id", projectId },
                            { "agent_name", "VortexenPlanSwiftConnector" },
                            { "machine_name", Environment.MachineName },
                            { "auto_reconcile", true },
                            { "payload", snapshot }
                        });
                        string resp = SecureBackendUploader.UploadSnapshot(
                            uploadUrl,
                            token,
                            ingestBody,
                            connectorSharedToken: connectorToken,
                            requireTls: !allowInsecureLocal);
                        Console.WriteLine("Upload & reconcile succeeded: " + resp);
                    }
                    return 0;
                }

                PrintUsage();
                return 1;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(CanonicalPayloadBuilder.SerializeJson(new
                {
                    error = ex.GetType().Name,
                    message = ex.Message
                }));
                return 3;
            }
        }

        private static string DeriveLoginUrl(string ingestUrl)
        {
            int idx = ingestUrl.IndexOf("/planswift/ingest", StringComparison.OrdinalIgnoreCase);
            if (idx >= 0)
            {
                return ingestUrl.Substring(0, idx) + "/auth/login/";
            }
            var uri = new Uri(ingestUrl);
            return uri.GetLeftPart(UriPartial.Authority) + "/api/v1/auth/login/";
        }

        private static int RunSelfTest()
        {
            if (!Environment.Is64BitProcess)
            {
                Console.Error.WriteLine("Self-test failed: connector must execute as a 64-bit process.");
                return 1;
            }

            var env = PlanSwiftVersionDetector.Detect();
            var sampleSnapshot = new ComExtractionSnapshot
            {
                source_system = "PlanSwiftCOM",
                connector_version = "1.2.4",
                extraction_scope = "full_job",
                planswift_version = "self-test",
                edition = "self-test",
                prog_id = env.RecommendedProgId ?? "unregistered",
                extracted_at_utc = DateTime.UtcNow.ToString("o"),
                read_only = true,
                project = new Dictionary<string, string>
                {
                    { "native_guid", "{00000000-0000-0000-0000-000000000000}" },
                    { "name", "SelfTest" }
                },
                objects = new List<ComExtractedObject>(),
                warnings = new List<string> { env.Notes }
            };

            string json = CanonicalPayloadBuilder.SerializeJson(sampleSnapshot);
            string digest = CanonicalPayloadBuilder.ComputeSha256Hex(json);
            Console.WriteLine(CanonicalPayloadBuilder.SerializeJson(new
            {
                self_test = "passed",
                version = "1.2.4",
                is_64_bit = Environment.Is64BitProcess,
                com_ready = env.ComReady,
                payload_sha256 = digest,
                environment = env
            }));
            return 0;
        }

        private static string GetArgValue(string[] args, string flag)
        {
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (string.Equals(args[i], flag, StringComparison.OrdinalIgnoreCase))
                {
                    return args[i + 1];
                }
            }
            return null;
        }

        private static bool HasFlag(string[] args, string flag)
        {
            foreach (var a in args)
            {
                if (string.Equals(a, flag, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }

        private static void PrintUsage()
        {
            Console.WriteLine("Vortexen PlanSwift Read-Only COM Connector v1.2.4 (x64)");
            Console.WriteLine("Usage:");
            Console.WriteLine("  VortexenPlanSwiftConnector.exe --health");
            Console.WriteLine("  VortexenPlanSwiftConnector.exe --detect [--progid <ProgID>]");
            Console.WriteLine("  VortexenPlanSwiftConnector.exe --self-test");
            Console.WriteLine("  VortexenPlanSwiftConnector.exe --extract-com [--pages-only] [--mode fast|full] [--include-points] [--skip-page-dimensions] [--allow-root] [--expected-guid <GUID>] [--connect-timeout <int>] [--max-seconds <int>] [--out <file.json>] [--upload-url <url> --project-id <uuid> (--token <jwt> | --email <e> --password <p>) [--allow-insecure-local]]");
        }
    }
}
