import { useState } from 'react'
import { isStatic, useSeats, useSnapshotMeta } from './api/client'

/** Use the latest exported composition offline, never a missing wall-clock date. */
export function useCurrentSeats() {
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const snapshot = useSnapshotMeta()
  const date = isStatic() ? snapshot.data?.composition_dates.at(-1) : today
  const seats = useSeats(date)
  return {
    ...seats,
    isLoading: seats.isLoading || snapshot.isLoading,
    isError: seats.isError || snapshot.isError,
  }
}
