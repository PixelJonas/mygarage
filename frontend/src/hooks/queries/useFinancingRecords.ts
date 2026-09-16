import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/services/api'
import type { FinancingRecordListResponse, FinancingRecordCreate, FinancingRecordUpdate } from '@/types/financing'

export function useFinancingRecords(vin: string) {
  return useQuery({
    queryKey: ['financingRecords', vin],
    queryFn: async () => {
      const { data } = await api.get<FinancingRecordListResponse>(
        `/vehicles/${vin}/financing-records`
      )
      return data
    },
    enabled: !!vin,
  })
}

export function useCreateFinancingRecord(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: FinancingRecordCreate) => {
      const { data } = await api.post(`/vehicles/${vin}/financing-records`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financingRecords', vin] })
    },
  })
}

export function useUpdateFinancingRecord(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }: FinancingRecordUpdate & { id: number }) => {
      const { data } = await api.put(`/vehicles/${vin}/financing-records/${id}`, payload)
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financingRecords', vin] })
    },
  })
}

export function useDeleteFinancingRecord(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (recordId: number) => {
      await api.delete(`/vehicles/${vin}/financing-records/${recordId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financingRecords', vin] })
    },
  })
}
