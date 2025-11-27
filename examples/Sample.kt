package com.example.kotlin

import java.util.Collections

/**
 * A sample Kotlin file to demonstrate analysis capabilities.
 */
data class User(
    val id: Long,
    val username: String,
    var email: String,
    val active: Boolean = true
)

interface Displayable {
    fun display(): String

    fun summary(): String {
        return "No summary"
    }
}

sealed class Result<out T> {
    data class Success<out T>(val data: T) : Result<T>()
    data class Error(val message: String) : Result<Nothing>()
}

class UserManager(private val db: Any?) : Displayable {

    val userCount: Int
        get() = 42 // Simulated

    fun getUser(id: Long): User? {
        return if (id > 0) User(id, "user$id", "user$id@example.com") else null
    }

    suspend fun fetchUserAsync(id: Long): Result<User> {
        // Simulate async work
        return Result.Success(User(id, "async_user", "async@example.com"))
    }

    override fun display(): String {
        return "UserManager managing users"
    }
}

object Config {
    const val MAX_USERS = 100
    val version = "1.0.0"
}
// Extension function
fun String.toTitleCase(): String {
    return this.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() }
}

// Annotation
@Deprecated("Use UserManager instead")
class LegacyUserManager {
    fun get() = "legacy"
}

fun main(args: Array<String>) {
    val manager = UserManager(null)
    println(manager.display())
}
