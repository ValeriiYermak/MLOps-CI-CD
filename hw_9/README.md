apiVersion: v1
kind: ServiceAccount
metadata:
  name: pod-cleanup
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pod-cleanup
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["list", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: pod-cleanup
subjects:
  - kind: ServiceAccount
    name: pod-cleanup
    namespace: kube-system
roleRef:
  kind: ClusterRole
  name: pod-cleanup
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: pod-cleanup
  namespace: kube-system
spec:
  # Кожні 2 хвилини - агресивніше за типове значення (5+ хв), свідомо,
  # щоб швидко звільняти обмежену кількість "слотів" подів на t3.micro
  # (ліміт ~4 поди/нода через обмеження ENI для AWS VPC CNI).
  schedule: "*/2 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: pod-cleanup
          restartPolicy: OnFailure
          containers:
            - name: cleanup
              image: bitnami/kubectl:latest
              command:
                - /bin/sh
                - -c
                - |
                  kubectl delete pods -A \
                    --field-selector=status.phase!=Running \
                    --field-selector=status.phase!=Pending \
                    --ignore-not-found