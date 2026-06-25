{{
   config(
        tags=['dataspherev2', 'silver'],
        alias='knkk',
        materialized='table',
    )
}}


SELECT
    {{ nullif_empty('MANDT') }} AS mandt,
    {{ nullif_empty('KUNNR') }} AS kunnr,
    {{ nullif_empty('KKBER') }} AS kkber,
    {{ to_decimal('KLIMK') }} AS klimk,
    {{ nullif_empty('KNKLI') }} AS knkli,
    {{ to_decimal('SAUFT') }} AS sauft,
    {{ to_decimal('SKFOR') }} AS skfor,
    {{ to_decimal('SSOBL') }} AS ssobl,
    {{ nullif_empty('UEDAT') }} AS uedat,
    {{ nullif_empty('XCHNG') }} AS xchng,
    {{ nullif_empty('ERNAM') }} AS ernam,
    {{ nullif_empty('ERDAT') }} AS erdat,
    {{ nullif_empty('CTLPC') }} AS ctlpc,
    {{ nullif_empty('DTREV') }} AS dtrev,
    {{ nullif_empty('CRBLB') }} AS crblb,
    {{ nullif_empty('SBGRP') }} AS sbgrp,
    {{ nullif_empty('NXTRV') }} AS nxtrv,
    {{ nullif_empty('KRAUS') }} AS kraus,
    {{ nullif_empty('PAYDB') }} AS paydb,
    {{ nullif_empty('DBRAT') }} AS dbrat,
    {{ nullif_empty('REVDB') }} AS revdb,
    {{ nullif_empty('AEDAT') }} AS aedat,
    {{ nullif_empty('AETXT') }} AS aetxt,
    {{ nullif_empty('GRUPP') }} AS grupp,
    {{ nullif_empty('AENAM') }} AS aenam,
    {{ nullif_empty('SBDAT') }} AS sbdat,
    {{ nullif_empty('KDGRP') }} AS kdgrp,
    {{ nullif_empty('CASHD') }} AS cashd,
    {{ to_decimal('CASHA') }} AS casha,
    {{ nullif_empty('CASHC') }} AS cashc,
    {{ nullif_empty('DBPAY') }} AS dbpay,
    {{ nullif_empty('DBRTG') }} AS dbrtg,
    {{ to_decimal('DBEKR') }} AS dbekr,
    {{ nullif_empty('DBWAE') }} AS dbwae,
    {{ nullif_empty('DBMON') }} AS dbmon,
    {{ to_decimal('ABSBT') }} AS absbt,

    -- Metadados de Auditoria da Pipeline
    {{ to_timestamp('dt_ingestao') }} AS dt_ingestao,
    hash_pk,
    source

FROM {{ source('dataspherev2', 'knkk') }}
