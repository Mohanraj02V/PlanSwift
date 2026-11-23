using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace Vortexen.PlanSwiftConnector
{
    public static class CanonicalPayloadBuilder
    {
        public static string SerializeJson(object payload)
        {
            var serializer = new JavaScriptSerializer
            {
                MaxJsonLength = 64 * 1024 * 1024
            };
            return serializer.Serialize(payload);
        }

        public static string ComputeSha256Hex(string utf8Payload)
        {
            using (var sha = SHA256.Create())
            {
                byte[] bytes = Encoding.UTF8.GetBytes(utf8Payload);
                byte[] hash = sha.ComputeHash(bytes);
                var sb = new StringBuilder(hash.Length * 2);
                foreach (byte b in hash)
                {
                    sb.Append(b.ToString("x2"));
                }
                return sb.ToString();
            }
        }

        public static void WriteJsonFile(string path, string json)
        {
            string dir = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }
            File.WriteAllText(path, json, new UTF8Encoding(false));
        }
    }
}
