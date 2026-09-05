import React, { useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, Alert } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import * as Haptics from "expo-haptics";
import { colors } from "../theme";
import { useAppState } from "../AppContext";
import { formatTry, formatDateTime, SITE_EMOJI } from "../format";

function haptic() {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
}

export default function HomeScreen({ navigation }) {
  const { totalValue, listings, newCount, scanActive, loading, stopScan, clearAll, refreshAll, apiBase } =
    useAppState();
  const [refreshing, setRefreshing] = useState(false);

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Günaydın" : hour < 18 ? "İyi günler" : "İyi akşamlar";

  const onRefresh = async () => {
    setRefreshing(true);
    await refreshAll();
    setRefreshing(false);
  };

  const handleStop = async () => {
    haptic();
    try {
      await stopScan();
    } catch (e) {
      Alert.alert("Hata", e.message);
    }
  };

  const handleClear = async () => {
    haptic();
    Alert.alert("Emin misiniz?", "Tüm bulunan araçlar silinecek.", [
      { text: "Vazgeç", style: "cancel" },
      {
        text: "Temizle",
        style: "destructive",
        onPress: async () => {
          try {
            await clearAll();
          } catch (e) {
            Alert.alert("Hata", e.message);
          }
        },
      },
    ]);
  };

  const recent = [...listings]
    .sort((a, b) => new Date(b.scraped_at || 0) - new Date(a.scraped_at || 0))
    .slice(0, 8);

  if (!apiBase) {
    return (
      <View style={styles.centerWrap}>
        <Text style={styles.emptyTitle}>API adresi ayarlanmamış</Text>
        <Text style={styles.emptyBody}>
          Devam etmek için Ayarlar sekmesinden bilgisayarınızın adresini girin (örn. http://192.168.1.10:8000).
        </Text>
        <TouchableOpacity style={styles.primaryBtn} onPress={() => navigation.navigate("Ayarlar")}>
          <Text style={styles.primaryBtnText}>Ayarlara Git</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={{ paddingBottom: 40 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.pink} />}
    >
      <View style={styles.topbar}>
        <View>
          <Text style={styles.greetingHello}>{greeting}</Text>
          <Text style={styles.greetingName}>Avcı Botu 🎯</Text>
        </View>
        <View style={styles.bellWrap}>
          <Text style={{ fontSize: 18 }}>🔔</Text>
          {newCount > 0 && <View style={styles.notifDot} />}
        </View>
      </View>

      <View style={styles.balanceBlock}>
        <Text style={styles.balanceLabel}>Toplam Tespit Edilen Değer</Text>
        <Text style={styles.balanceAmount}>₺{formatTry(totalValue)}</Text>
      </View>

      <View style={styles.heroWrap}>
        <LinearGradient colors={[colors.violet, colors.pink]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.heroCard}>
          <View style={styles.heroTop}>
            <View style={styles.chip} />
            <Text style={styles.heroBrand}>OTOGALERİ</Text>
          </View>
          <Text style={styles.heroNumber}>•••• MOB</Text>
        </LinearGradient>
      </View>

      <View style={styles.quickActions}>
        <QuickAction emoji="▶️" label="Başlat" onPress={() => { haptic(); navigation.navigate("Filtreler"); }} />
        <QuickAction emoji="⏹" label="Durdur" disabled={!scanActive || loading} onPress={handleStop} />
        <QuickAction emoji="🧹" label="Temizle" disabled={listings.length === 0 || loading} onPress={handleClear} />
        <QuickAction emoji="🔄" label="Yenile" onPress={() => { haptic(); refreshAll(); }} />
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Son Bulunanlar</Text>
        {recent.length === 0 ? (
          <Text style={styles.emptyRow}>Henüz araç bulunamadı</Text>
        ) : (
          recent.map((row, idx) => {
            const isNew = row.is_new_listing === 1 || row.is_new_listing === true;
            return (
              <View key={row.id ?? idx} style={styles.txRow}>
                <View style={styles.txEmoji}>
                  <Text>{SITE_EMOJI[row.source_site] || "🚘"}</Text>
                </View>
                <View style={styles.txInfo}>
                  <Text style={styles.txName} numberOfLines={1}>
                    {row.brand} {row.model}
                  </Text>
                  <Text style={styles.txTime}>
                    {row.source_site} · {formatDateTime(row.scraped_at)}
                  </Text>
                </View>
                <Text style={[styles.txAmount, isNew && { color: colors.green }]}>
                  {isNew ? "+" : "-"}₺{formatTry(row.price)}
                </Text>
              </View>
            );
          })
        )}
      </View>
    </ScrollView>
  );
}

function QuickAction({ emoji, label, onPress, disabled }) {
  return (
    <TouchableOpacity style={styles.qaWrap} onPress={onPress} disabled={disabled} activeOpacity={0.7}>
      <View style={[styles.qaBtn, disabled && { opacity: 0.35 }]}>
        <Text style={{ fontSize: 19 }}>{emoji}</Text>
      </View>
      <Text style={styles.qaLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.navy },
  centerWrap: { flex: 1, backgroundColor: colors.navy, alignItems: "center", justifyContent: "center", padding: 32 },
  emptyTitle: { color: colors.white, fontSize: 18, fontWeight: "600", marginBottom: 8, textAlign: "center" },
  emptyBody: { color: colors.muted, fontSize: 14, textAlign: "center", marginBottom: 20, lineHeight: 20 },
  primaryBtn: {
    borderRadius: 50,
    paddingVertical: 12,
    paddingHorizontal: 24,
    backgroundColor: colors.violet,
  },
  primaryBtnText: { color: colors.white, fontWeight: "600" },
  topbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 20,
  },
  greetingHello: { color: colors.muted, fontSize: 13 },
  greetingName: { color: colors.white, fontSize: 20, fontWeight: "600" },
  bellWrap: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  notifDot: {
    position: "absolute",
    top: 6,
    right: 7,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.red,
  },
  balanceBlock: { alignItems: "center", marginBottom: 24 },
  balanceLabel: { color: colors.muted, fontSize: 13, marginBottom: 6 },
  balanceAmount: { color: colors.white, fontSize: 32, fontWeight: "700" },
  heroWrap: { alignItems: "center", marginBottom: 28 },
  heroCard: {
    width: 200,
    height: 126,
    borderRadius: 14,
    padding: 16,
    justifyContent: "space-between",
    transform: [{ rotate: "-6deg" }],
  },
  heroTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  chip: { width: 26, height: 20, borderRadius: 4, backgroundColor: "#e6c874" },
  heroBrand: { color: colors.white, fontSize: 13, fontWeight: "700", letterSpacing: 1.5 },
  heroNumber: { color: "rgba(255,255,255,0.95)", fontSize: 14, fontWeight: "600", letterSpacing: 1.5 },
  quickActions: {
    flexDirection: "row",
    justifyContent: "space-around",
    marginBottom: 32,
    paddingHorizontal: 12,
  },
  qaWrap: { alignItems: "center", gap: 6 },
  qaBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  qaLabel: { color: "#c7cae3", fontSize: 12 },
  section: { paddingHorizontal: 20 },
  sectionTitle: { color: colors.white, fontSize: 17, fontWeight: "600", marginBottom: 12 },
  emptyRow: { color: colors.muted, fontSize: 14, paddingVertical: 12 },
  txRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 11,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(255,255,255,0.05)",
  },
  txEmoji: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: "center",
    justifyContent: "center",
  },
  txInfo: { flex: 1, minWidth: 0 },
  txName: { color: colors.white, fontSize: 14.5, fontWeight: "500" },
  txTime: { color: colors.muted, fontSize: 12.5, marginTop: 2 },
  txAmount: { color: colors.white, fontSize: 15, fontWeight: "700" },
});
