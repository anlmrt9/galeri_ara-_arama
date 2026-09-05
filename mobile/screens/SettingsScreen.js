import React, { useState, useEffect } from "react";
import { View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator, ScrollView } from "react-native";
import { colors } from "../theme";
import { useAppState } from "../AppContext";
import { checkHealth } from "../api";

export default function SettingsScreen() {
  const { apiBase, updateApiBase, refreshAll, connectionError } = useAppState();
  const [input, setInput] = useState(apiBase);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  useEffect(() => {
    setInput(apiBase);
  }, [apiBase]);

  const handleSave = async () => {
    await updateApiBase(input);
    setTestResult(null);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await updateApiBase(input);
      const res = await checkHealth();
      setTestResult(res.db_connected ? "✅ Bağlantı başarılı, veritabanı hazır." : "⚠️ Sunucuya ulaşıldı ama veritabanı bağlı değil.");
      await refreshAll();
    } catch (e) {
      setTestResult(`❌ Bağlantı hatası: ${e.message}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 20 }}>
      <Text style={styles.header}>⚙️ Bağlantı Ayarları</Text>
      <Text style={styles.helperText}>
        Bilgisayarınızda çalışan OtoGaleri API sunucusunun adresini girin. Aynı Wi-Fi ağındaysanız yerel ağ
        adresini kullanabilirsiniz (örn. http://192.168.1.10:8000).
      </Text>

      <Text style={styles.label}>API Adresi</Text>
      <TextInput
        style={styles.input}
        value={input}
        onChangeText={setInput}
        placeholder="http://192.168.1.10:8000"
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
      />

      <View style={styles.row}>
        <TouchableOpacity style={styles.secondaryBtn} onPress={handleSave}>
          <Text style={styles.secondaryBtnText}>Kaydet</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.primaryBtn} onPress={handleTest} disabled={testing}>
          {testing ? <ActivityIndicator color={colors.white} /> : <Text style={styles.primaryBtnText}>Bağlantıyı Test Et</Text>}
        </TouchableOpacity>
      </View>

      {testResult && <Text style={styles.testResult}>{testResult}</Text>}
      {connectionError && !testResult && <Text style={styles.testResultError}>Son hata: {connectionError}</Text>}

      <View style={styles.infoBox}>
        <Text style={styles.infoTitle}>Nasıl bulunur?</Text>
        <Text style={styles.infoText}>
          Bilgisayarınızda backend'i başlatın:{"\n"}
          <Text style={styles.code}>python -m uvicorn api:app --host 0.0.0.0 --port 8000</Text>
          {"\n\n"}Windows'ta yerel ağ IP adresinizi görmek için komut istemine <Text style={styles.code}>ipconfig</Text> yazın ve
          "IPv4 Address" satırını kullanın.
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.navy },
  header: { color: colors.white, fontSize: 18, fontWeight: "600", marginBottom: 10 },
  helperText: { color: colors.muted, fontSize: 13, lineHeight: 19, marginBottom: 20 },
  label: { color: "#c7cae3", fontSize: 13, marginBottom: 6 },
  input: {
    backgroundColor: colors.surface,
    color: colors.white,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: 16,
  },
  row: { flexDirection: "row", gap: 12 },
  secondaryBtn: {
    flex: 1,
    borderRadius: 50,
    paddingVertical: 13,
    alignItems: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  secondaryBtnText: { color: colors.white, fontWeight: "600" },
  primaryBtn: {
    flex: 1,
    borderRadius: 50,
    paddingVertical: 13,
    alignItems: "center",
    backgroundColor: colors.violet,
  },
  primaryBtnText: { color: colors.white, fontWeight: "600" },
  testResult: { color: colors.white, marginTop: 16, fontSize: 13, lineHeight: 19 },
  testResultError: { color: colors.red, marginTop: 16, fontSize: 13, lineHeight: 19 },
  infoBox: {
    marginTop: 30,
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: colors.border,
  },
  infoTitle: { color: colors.white, fontWeight: "600", marginBottom: 8 },
  infoText: { color: colors.muted, fontSize: 12.5, lineHeight: 19 },
  code: { color: colors.pink, fontFamily: "monospace" },
});
