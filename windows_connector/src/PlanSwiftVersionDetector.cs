using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32;

namespace Vortexen.PlanSwiftConnector
{
    public sealed class EnvironmentDetectionResult
    {
        public string OsVersion { get; set; }
        public bool Is64BitProcess { get; set; }
        public bool IsUserInteractive { get; set; }
        public string WindowsIdentity { get; set; }
        public List<string> RegisteredProgIds { get; set; }
        public string RecommendedProgId { get; set; }
        public string DetectedGeneration { get; set; }
        public bool ComReady { get; set; }
        public string Notes { get; set; }
    }

    public static class PlanSwiftVersionDetector
    {
        private static readonly string[] KnownProgIds = new[]
        {
            "PlanSwift.PlanSwift12",
            "PlanSwift9.PlanSwift",
            "PlanSwift.Application"
        };

        public static EnvironmentDetectionResult Detect(string overrideProgId = null)
        {
            var found = new List<string>();
            var candidates = string.IsNullOrWhiteSpace(overrideProgId)
                ? KnownProgIds
                : new[] { overrideProgId };

            foreach (var progId in candidates)
            {
                if (IsProgIdRegistered(progId))
                {
                    found.Add(progId);
                }
            }

            string recommended = found.Count > 0 ? found[0] : null;
            string generation = "None";
            bool comReady = false;
            string notes;

            if (recommended == null)
            {
                notes = "No PlanSwift COM ProgID found in HKCR. Install PlanSwift Desktop (11 or 12+) on this Windows workstation.";
            }
            else if (string.Equals(recommended, "PlanSwift.PlanSwift12", StringComparison.OrdinalIgnoreCase))
            {
                generation = "PlanSwift 12+ (64-bit)";
                if (!Environment.Is64BitProcess)
                {
                    notes = "PlanSwift 12 requires a 64-bit client process (-platform:x64).";
                }
                else if (!Environment.UserInteractive)
                {
                    notes = "PlanSwift COM requires an interactive signed-in Windows user session.";
                }
                else
                {
                    comReady = true;
                    notes = "PlanSwift 12 ProgID registered and x64 interactive process verified.";
                }
            }
            else
            {
                generation = "PlanSwift 9-11 (Legacy 32-bit / Out-of-process COM)";
                comReady = Environment.UserInteractive;
                notes = Environment.UserInteractive
                    ? "Legacy PlanSwift ProgID registered. Ensure PlanSwift is open and user is signed in."
                    : "PlanSwift COM requires an interactive signed-in Windows user session.";
            }

            string identity = "";
            try
            {
                identity = WindowsIdentity.GetCurrent().Name;
            }
            catch
            {
                identity = Environment.UserName;
            }

            return new EnvironmentDetectionResult
            {
                OsVersion = Environment.OSVersion.ToString(),
                Is64BitProcess = Environment.Is64BitProcess,
                IsUserInteractive = Environment.UserInteractive,
                WindowsIdentity = identity,
                RegisteredProgIds = found,
                RecommendedProgId = recommended,
                DetectedGeneration = generation,
                ComReady = comReady,
                Notes = notes
            };
        }

        private static bool IsProgIdRegistered(string progId)
        {
            try
            {
                using (var key = Registry.ClassesRoot.OpenSubKey(progId))
                {
                    if (key != null) return true;
                }
            }
            catch
            {
                // Ignore permission-restricted registry keys safely
            }

            try
            {
                return Type.GetTypeFromProgID(progId, false) != null;
            }
            catch
            {
                return false;
            }
        }
    }
}
