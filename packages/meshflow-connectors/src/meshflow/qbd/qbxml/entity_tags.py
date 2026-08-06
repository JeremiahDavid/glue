from meshflow.qbd.models import EntityType

RET_TAG: dict[EntityType, str] = {
    EntityType.COMPANY: "CompanyRet",
    EntityType.ACCOUNT: "AccountRet",
    EntityType.CLASS: "ClassRet",
    EntityType.DEPARTMENT: "DepartmentRet",
    EntityType.CUSTOMER: "CustomerRet",
    EntityType.VENDOR: "VendorRet",
    EntityType.ITEM: "ItemRet",
    EntityType.INVOICE: "InvoiceRet",
    EntityType.BILL: "BillRet",
    EntityType.SALES_RECEIPT: "SalesReceiptRet",
    EntityType.CREDIT_MEMO: "CreditMemoRet",
    EntityType.DEPOSIT: "DepositRet",
    EntityType.RECEIVE_PAYMENT: "ReceivePaymentRet",
    EntityType.ESTIMATE: "EstimateRet",
}
