using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace Vortexen.PlanSwiftConnector
{
    public static class SecureBackendUploader
    {
        public static string LoginForAccessToken(string loginUrl, string email, string password, bool requireTls = true)
        {
            Uri uri;
            if (!Uri.TryCreate(loginUrl, UriKind.Absolute, out uri))
            {
                throw new ArgumentException("Invalid login URL.");
            }
            if (requireTls && !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("Refusing unencrypted login when requireTls=true. Pass --allow-insecure-local for localhost.");
            }

            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            var serializer = new JavaScriptSerializer();
            string payload = serializer.Serialize(new Dictionary<string, string>
            {
                { "email", email },
                { "password", password }
            });

            using (var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) })
            using (var content = new StringContent(payload, Encoding.UTF8, "application/json"))
            {
                var response = client.PostAsync(uri, content).GetAwaiter().GetResult();
                string body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                if (!response.IsSuccessStatusCode)
                {
                    throw new HttpRequestException(string.Format("Login failed HTTP {0}: {1}", (int)response.StatusCode, body));
                }
                var parsed = serializer.Deserialize<Dictionary<string, object>>(body);
                if (parsed == null || !parsed.ContainsKey("access"))
                {
                    throw new InvalidOperationException("Login response did not contain access token.");
                }
                return Convert.ToString(parsed["access"]);
            }
        }

        public static string UploadSnapshot(
            string endpointUrl,
            string bearerToken,
            string jsonPayload,
            string connectorSharedToken = null,
            bool requireTls = true,
            int maxRetries = 3)
        {
            Uri uri;
            if (!Uri.TryCreate(endpointUrl, UriKind.Absolute, out uri))
            {
                throw new ArgumentException("Invalid upload URL.");
            }
            if (requireTls && !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "Refusing unencrypted HTTP upload when requireTls=true. Use https:// or pass --allow-insecure-local for localhost.");
            }

            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            string digest = CanonicalPayloadBuilder.ComputeSha256Hex(jsonPayload);

            using (var client = new HttpClient { Timeout = TimeSpan.FromSeconds(120) })
            {
                if (!string.IsNullOrWhiteSpace(bearerToken))
                {
                    client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", bearerToken);
                }
                if (!string.IsNullOrWhiteSpace(connectorSharedToken))
                {
                    client.DefaultRequestHeaders.Add("X-Connector-Token", connectorSharedToken);
                }
                client.DefaultRequestHeaders.Add("X-Payload-SHA256", digest);

                Exception lastErr = null;
                for (int attempt = 1; attempt <= maxRetries; attempt++)
                {
                    try
                    {
                        using (var content = new StringContent(jsonPayload, Encoding.UTF8, "application/json"))
                        {
                            var response = client.PostAsync(uri, content).GetAwaiter().GetResult();
                            string body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
                            if (response.IsSuccessStatusCode)
                            {
                                return body;
                            }
                            lastErr = new HttpRequestException(
                                string.Format("HTTP {0}: {1}", (int)response.StatusCode, body));
                        }
                    }
                    catch (Exception ex)
                    {
                        lastErr = ex;
                    }
                    if (attempt < maxRetries)
                    {
                        Thread.Sleep(500 * attempt);
                    }
                }
                throw lastErr ?? new InvalidOperationException("Upload failed.");
            }
        }
    }
}
