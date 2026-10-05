import { Center, Loader } from '@mantine/core'
import { Shell } from './components/layout/Shell'
import { LoginScreen } from './components/auth/LoginScreen'
import { useAuth } from './hooks/useAuth'
import { useHashRoute } from './hooks/useHashRoute'
import { SummaryScreen } from './screens/summary/SummaryScreen'
import { UploadScreen } from './screens/upload/UploadScreen'
import { PlanScreen } from './screens/plan/PlanScreen'
import { RisksScreen } from './screens/risks/RisksScreen'
import { StarMapScreen } from './screens/starmap/StarMapScreen'
import { KpiScreen } from './screens/kpi/KpiScreen'
import { RolesScreen } from './screens/roles/RolesScreen'
import { ProfilesScreen } from './screens/profiles/ProfilesScreen'
import { DataQualityScreen } from './screens/data/DataQualityScreen'

export default function App() {
  const [screen, go] = useHashRoute()
  const { isLoading, needsLogin } = useAuth()

  if (needsLogin) return <LoginScreen />
  if (isLoading) {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    )
  }

  return (
    <Shell screen={screen} onNavigate={go}>
      {screen === 'summary' && <SummaryScreen onNavigate={go} />}
      {screen === 'upload' && <UploadScreen onOpenPlan={() => go('plan')} />}
      {screen === 'plan' && <PlanScreen />}
      {screen === 'risks' && <RisksScreen />}
      {screen === 'starmap' && <StarMapScreen />}
      {screen === 'kpi' && <KpiScreen />}
      {screen === 'roles' && <RolesScreen />}
      {screen === 'profiles' && <ProfilesScreen />}
      {screen === 'data' && <DataQualityScreen />}
    </Shell>
  )
}
