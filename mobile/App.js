import React from "react";
import { StatusBar } from "expo-status-bar";
import { NavigationContainer, DarkTheme } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { Text } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { colors } from "./theme";
import { AppStateProvider } from "./AppContext";
import HomeScreen from "./screens/HomeScreen";
import FiltersScreen from "./screens/FiltersScreen";
import ResultsScreen from "./screens/ResultsScreen";
import SettingsScreen from "./screens/SettingsScreen";

const Tab = createBottomTabNavigator();

const navTheme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: colors.navy,
    card: colors.surface,
    text: colors.white,
    border: colors.border,
    primary: colors.pink,
  },
};

const TAB_ICONS = {
  "Ana Sayfa": "🏠",
  Filtreler: "🎯",
  Sonuçlar: "📊",
  Ayarlar: "⚙️",
};

export default function App() {
  return (
    <SafeAreaProvider>
      <AppStateProvider>
        <NavigationContainer theme={navTheme}>
          <StatusBar style="light" backgroundColor={colors.navy} />
          <Tab.Navigator
            screenOptions={({ route }) => ({
              headerStyle: { backgroundColor: colors.navy },
              headerTintColor: colors.white,
              headerShadowVisible: false,
              tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
              tabBarActiveTintColor: colors.pink,
              tabBarInactiveTintColor: colors.muted,
              tabBarIcon: () => <Text style={{ fontSize: 18 }}>{TAB_ICONS[route.name]}</Text>,
            })}
          >
            <Tab.Screen name="Ana Sayfa" component={HomeScreen} />
            <Tab.Screen name="Filtreler" component={FiltersScreen} />
            <Tab.Screen name="Sonuçlar" component={ResultsScreen} />
            <Tab.Screen name="Ayarlar" component={SettingsScreen} />
          </Tab.Navigator>
        </NavigationContainer>
      </AppStateProvider>
    </SafeAreaProvider>
  );
}
