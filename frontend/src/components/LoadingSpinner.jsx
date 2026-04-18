export default function LoadingSpinner({ message = 'Loading products...' }) {
  return (
    <div className="flex flex-col items-center gap-4 py-20">
      <div className="relative w-14 h-14">
        <div className="absolute inset-0 border-4 border-gold-500/20 rounded-full" />
        <div className="absolute inset-0 border-4 border-transparent border-t-gold-500 rounded-full animate-spin" />
      </div>
      <p className="text-gray-500 text-sm">{message}</p>
    </div>
  )
}
