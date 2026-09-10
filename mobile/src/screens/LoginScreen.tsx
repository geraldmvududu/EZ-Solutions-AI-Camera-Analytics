import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";

export function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleLogin() {
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to reach the server");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>EZ SOLUTIONS</Text>
      <Text style={styles.subtitle}>AI Camera Analytics</Text>

      <View style={styles.card}>
        {error && <Text style={styles.error}>{error}</Text>}
        <Text style={styles.label}>Email</Text>
        <TextInput
          style={styles.input}
          autoCapitalize="none"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
          placeholder="admin@ezsolutions.local"
          placeholderTextColor="#5a6472"
        />
        <Text style={styles.label}>Password</Text>
        <TextInput style={styles.input} secureTextEntry value={password} onChangeText={setPassword} placeholderTextColor="#5a6472" />

        <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={submitting}>
          {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Sign in</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0e14", justifyContent: "center", padding: 24 },
  title: { color: "#f1f5f9", fontSize: 28, fontWeight: "700", textAlign: "center" },
  subtitle: { color: "#14b8a6", textAlign: "center", marginBottom: 32, fontWeight: "600" },
  card: { backgroundColor: "#151b2b", borderRadius: 12, padding: 20, borderWidth: 1, borderColor: "#1e2638" },
  label: { color: "#94a3b8", fontSize: 12, marginBottom: 4, marginTop: 12 },
  input: { backgroundColor: "#0f1420", borderWidth: 1, borderColor: "#2a3448", borderRadius: 8, padding: 10, color: "#f1f5f9" },
  button: { backgroundColor: "#0d9488", borderRadius: 8, padding: 14, alignItems: "center", marginTop: 20 },
  buttonText: { color: "#fff", fontWeight: "700" },
  error: { color: "#ef4444", marginBottom: 8 },
});
